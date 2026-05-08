import asyncio
import json
import time
import random
import re
from typing import List, Optional, Union
import requests
from markdownify import markdownify as md
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore


from db.models.opinion_tracking import OpinionTrackingInDB
from util.settings import settings
from db.models.legal_subject import LegalSubjectInDB
from db.models.court_opinion import CourtOpinion, CourtOpinionInDB
from db.connection import court_opinion_repo, legal_subject_repo, opinion_tracking_repo
from agents.post_migration_agent import get_migration_extraction_agent, user_prompt as migration_user_prompt
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__, "INFO")

# --- Configuration ---
WP_URL = settings.wp_base_url
WP_USER = settings.wp_username
WP_APP_PASSWORD = settings.wp_app_password

# --- Google Indexing ---
GOOGLE_CREDENTIALS_FILE = settings.json_keyfile
SCOPES = ["https://www.googleapis.com/auth/indexing"]
API_SERVICE_NAME = "indexing"
API_VERSION = "v3"

class QuotaExceededError(Exception):
    """Raised when the Daily Limit is reached."""
    pass

ai_client = OpenAI(api_key=settings.openai_api_key)

def get_tag_id(tag_slug: str) -> Union[int, None]:
    """Fetch the ID of a tag given its slug."""
    response = requests.get(f"{WP_URL}/tags?slug={tag_slug}", auth=(WP_USER, WP_APP_PASSWORD))
    tags = response.json()
    if tags:
        return tags[0]['id']
    return None

def get_posts_to_process(tag_slug: str, status: str = 'publish', per_page: int = 100) -> List[dict[str, str]]:
    """
    Fetch all posts with specific tag and status, paginating through all pages.

        Args:
            tag_slug: The slug of the tag to filter posts by.
            status: The post status to filter by (default: 'publish').
            per_page: Number of posts per page (default/max: 100).
        Returns:
            A list of all posts matching the criteria across all pages.
    """
    tag_id = get_tag_id(tag_slug) or 0
    all_posts: List[dict[str, str]] = []
    page = 1

    while True:
        params: dict[str, Union[str, int]] = {
            'status': status, 'tags': tag_id, 'context': 'edit',
            'per_page': per_page, 'page': page
        }
        resp = requests.get(f"{WP_URL}/posts", params=params, auth=(WP_USER, WP_APP_PASSWORD))
        posts = resp.json()
        if not posts:
            break
        all_posts.extend(posts)
        total_pages = int(resp.headers.get('X-WP-TotalPages', 1))
        if page >= total_pages:
            break
        page += 1

    logger.info("Fetched %d posts with tag '%s' and status '%s'", len(all_posts), tag_slug, status)
    return all_posts

def get_posts_to_index() -> List[CourtOpinionInDB]:
    """Fetch opinions that need Google indexing."""
    opionions_list: List[CourtOpinionInDB] = []

    opinions, _ = court_opinion_repo.select_many({"needs_review": False, "google_index_requested_at": None})
    opionions_list.extend(opinions)
    while True:
        opinions, _ = court_opinion_repo.select_many(
            {"needs_review": False, "google_index_requested_at": None},
            start=len(opionions_list),
            end=len(opionions_list) + 100
        )
        if not opinions:
            break
        opionions_list.extend(opinions)
    return opionions_list

def opinion_url(opinion: CourtOpinionInDB) -> str:
    """Construct the URL for a given opinion."""
    return f"https://www.txfamlaw.com/opinions/{opinion.slug}"

def clean_text(text: Union[str, None]) -> str:
    """
    Clean text by removing invalid unicode characters.
    """
    if text is None:
        return ""
    # Remove invalid unicode characters
    response = text.encode('utf-8', 'ignore').decode('utf-8', 'ignore')
    return response

def find_case_key(text: str) -> str:
    # case_key is a UUID inside double angle brackets, e.g. "<<uuid>>"
    match = re.search(r"~~([0-9a-fA-F-]{36})~~", text)
    if match:
        return match.group(1)
    return ""

# --- GOOGLE INDEXING ---
class IndexRequest:
    def __init__(self, url: str, slug: str):
        self.url = url
        self.slug = slug
        self.type = "URL_UPDATED"
        self.success = False
        self.message = ""


def index_opinions_with_google():
    logger.info("Starting Google indexing...")
    opinions_to_index = get_posts_to_index()
    url_batch_size = 100
    url_batch: list[IndexRequest] = []
    
    try:
        for opinion in opinions_to_index:
            url = opinion_url(opinion)
            url_batch.append(IndexRequest(url, opinion.slug))
            if len(url_batch) >= url_batch_size:
                notify_google_indexing(url_batch)
                url_batch = []
        
        if url_batch:
            notify_google_indexing(url_batch)
            
    except QuotaExceededError:
        logger.warning("Indexing halted: Daily quota met.")
    
    logger.info("Completed Google indexing session.")

def notify_google_indexing(urls: list[IndexRequest]) -> bool:
    # We keep track of which URLs still need to be processed
    pending_urls = {u.slug: u for u in urls}
    max_retries = 5
    retry_delay = 2 
    
    credentials = service_account.Credentials.from_service_account_file(  # type: ignore
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)  # type: ignore

    for attempt in range(max_retries):
        if not pending_urls:
            break

        # Local state for this specific batch execution
        results: dict[str, Union[list[str], bool]] = {
            "success_ids": [],
            "rate_limit_hit": False,
            "daily_limit_hit": False
        }

        def batch_callback(request_id: str, response: dict[str, str], exception: HttpError | None):
            if exception:
                # exception.content is a JSON byte string
                error_details = json.loads(exception.content).get('error', {})
                errors = error_details.get('details', [{}])
                reason = errors[0].get('reason', '')
                logger.error(f"Error for {request_id}: {reason}")

                status = exception.resp.status  # type: ignore

                # I don't think Google differentiates between rate limit and daily limit in their error responses. TJD 2026.03.20
                if reason == 'DAILY_LIMIT_EXCEEDED':
                    results["daily_limit_hit"] = True
                elif reason == 'RATE_LIMIT_EXCEEDED':
                    results["rate_limit_hit"] = True
                else:
                    logger.error(f"Permanent error {status} / {reason} for {request_id}")
            else:
                results["success_ids"].append(request_id)  # type: ignore

        # Build and execute the batch for remaining pending URLs
        batch = service.new_batch_http_request(callback=batch_callback)  # type: ignore
        for slug, req in pending_urls.items():
            body = {"url": req.url, "type": "URL_UPDATED"}
            batch.add(service.urlNotifications().publish(body=body), request_id=slug)  # type: ignore
        
        batch.execute()  # type: ignore

        # 1. Remove successful slugs from pending
        for slug in results["success_ids"]:  # type: ignore
            court_opinion_repo.update_google_index_requested_at(slug)  # type: ignore
            pending_urls.pop(slug, None)  # type: ignore

        # 2. Handle Daily Limit - Stop everything
        if results["daily_limit_hit"]:
            logger.error("Daily quota reached. stopping indexing workflow.")
            raise QuotaExceededError("Google Indexing Daily Limit Reached")

        # 3. Handle Rate Limit - Back off and retry
        if results["rate_limit_hit"] and pending_urls:
            wait = retry_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"Rate limit hit. {len(pending_urls)} URLs pending. Backing off {wait:.2f}s...")
            time.sleep(wait)
            continue 
        
        # If no rate limits were hit and we didn't finish everything, 
        # it means the remaining pending_urls had other errors.
        if not results["rate_limit_hit"]:
            break

    return len(pending_urls) == 0
async def delete_empty_opinions():
    logger.info("Checking for empty opinions to delete...")
    posts = get_posts_to_process(settings.wp_coatx_tag, status='draft')
    logger.info(f"Found {len(posts)} draft posts with tag '{settings.wp_coatx_tag}' to check for emptiness.")

    for post in posts:
        content = post['content']['raw']  # type: ignore
        if not content.strip() or content.strip().startswith("<p>None</p>"):
            pattern = re.compile(r'~~([0-9a-fA-F-]{36})~~')
            match = pattern.search(content)
            if match:
                case_key = match.group(1)
                logger.info(f"Post {post['id']} has empty content and case key {case_key}. Deleting post.")
                requests.delete(f"{WP_URL}/posts/{post['id']}", auth=(WP_USER, WP_APP_PASSWORD))
                logger.info("Deleting database records for case key %s", case_key)
                try:
                    opinion_tracking_repo.delete_by_case_key(case_key)
                except ValueError as e:
                    logger.warning(e)
                try:
                    court_opinion_repo.delete_by_case_key(case_key)
                except ValueError as e:
                    logger.warning(e)
            else:
                logger.warning(f"Post {post['id']} has empty content but no case key found. Skipping deletion.")

    logger.info("Completed checking for empty opinions.")

async def process_workflow():
    categories_in_db: List[LegalSubjectInDB]
    categories_in_db, _ = legal_subject_repo.select_many({})  # type: ignore
    defined_categories = [cat.id for cat in categories_in_db]
    DEFINED_CATEGORIES = ", ".join(defined_categories)
    tag_to_publish = settings.wp_post_tag
    tag_id_to_publish = get_tag_id(tag_to_publish)
    tag_to_mark_error = settings.wp_error_tag
    tag_id_to_mark_error = get_tag_id(tag_to_mark_error)
    tag_to_mark_success = settings.wp_success_tag
    tag_id_to_mark_success = get_tag_id(tag_to_mark_success)
    posts = get_posts_to_process(tag_to_publish)

    def _tag_migration_error(post: dict[str, str]):
        current_tags: list[int] = post['tags']  # type: ignore
        if tag_id_to_mark_error and tag_id_to_mark_error not in current_tags:
            current_tags.append(tag_id_to_mark_error)
        requests.post(f"{WP_URL}/posts/{post['id']}",
                    json={'tags': current_tags},
                    auth=(WP_USER, WP_APP_PASSWORD))

    successfully_uploaded = 0

    for post in posts:
        try:
            # 0. See if we should skip due to prior error
            current_tags: list[int] = post['tags']  # type: ignore
            if tag_id_to_mark_error and tag_id_to_mark_error in current_tags:
                logger.info("Skipping post %s due to prior error tag.", post.get('id'))
                continue

            logger.info("Processing post %s", post.get('id'))

            # 1. Convert WP HTML to Clean Markdown
            raw_html = post['content']['raw']  # type: ignore
            markdown_body = md(raw_html, strip=['script', 'style'], heading_style="ATX")

            # 2. Find the tracked opinion in the database using the case key
            headline = post['title']['rendered']  # type: ignore

            case_key = find_case_key(markdown_body)
            try:
                tracked_opinion: Optional[OpinionTrackingInDB] = opinion_tracking_repo.select_one(condition={"case_key": case_key})
            except Exception as e:
                logger.error(e)
                tracked_opinion = None
            if not tracked_opinion:
                logger.warning("No tracked opinion found for case key: %s", case_key)
                _tag_migration_error(post)
                continue
            logger.info("Found tracked opinion for case key: %s", case_key)

            # 3. Make sure the tracked_opinion.opinion_link does not already exist in the court_opinion table to avoid duplicates
            existing_opinion = court_opinion_repo.select_one(condition={"opinion_link": tracked_opinion.opinion_link})
            if existing_opinion:
                logger.warning("An opinion with the same opinion_link already exists in court_opinion for case key: %s. Skipping to avoid duplicate.", case_key)
                _tag_migration_error(post)
                continue

            # 4. Run the migration extraction agent to extract structured data and assign a category
            prompt = migration_user_prompt.format(
                headline=headline,
                markdown_body=markdown_body,
                defined_categories=DEFINED_CATEGORIES
            )
            logger.info("Running migration extraction agent for post %s", post.get('id'))
            response = await get_migration_extraction_agent().run(user_prompt=prompt)
            migration_data = response.output

            # 5. Save to Supabase
            opinion = CourtOpinion(
                case_name=clean_text(tracked_opinion.case_name),
                court=clean_text(tracked_opinion.court),
                lower_court_name=clean_text(tracked_opinion.lower_court_name),
                date=tracked_opinion.opinion_date,
                summary=clean_text(migration_data.brief_summary),
                litigation_takeaway=clean_text(migration_data.litigation_takeaway),
                slug=clean_text(migration_data.slug),
                category=clean_text(migration_data.category),
                citation=clean_text(migration_data.citation),
                opinion_link=clean_text(tracked_opinion.opinion_link),
                blog_post=clean_text(markdown_body),
                case_key=case_key,
                needs_review=True,
                q_and_a=tracked_opinion.q_and_a,
                has_substance=tracked_opinion.has_substance,
                seo_title=tracked_opinion.seo_title,
                seo_focus_kw=tracked_opinion.seo_focus_kw,
                meta_description=tracked_opinion.meta_description
            )

            try:
                logger.info("Inserting opinion for case %s into Supabase.", tracked_opinion.case_name)
                court_opinion_repo.insert(opinion.model_dump(mode="json"))
                logger.info("Saved %s to Supabase.", tracked_opinion.case_name)

                # 6. Remove the tag from WordPress so it doesn't process again
                current_tags: list[int] = post['tags']  # type: ignore
                new_tags = [t for t in current_tags if t != tag_id_to_publish]
                if tag_id_to_mark_success and tag_id_to_mark_success not in new_tags:
                    new_tags.append(tag_id_to_mark_success)

                logger.info("Updated tags for post %s to %s...migrating to WP", post.get('id'), new_tags)
                requests.post(f"{WP_URL}/posts/{post['id']}",
                            json={'tags': new_tags},
                            auth=(WP_USER, WP_APP_PASSWORD))
                successfully_uploaded += 1
            except Exception as db_e:
                logger.error("DB Error on post %s: %s", post.get('id'), db_e)
                _tag_migration_error(post)

        except Exception as e:
            logger.error("Error on post %s: %s", post.get('id'), e)
            logger.exception(e)

    # 7. After processing all posts, trigger Google indexing for the newly migrated opinions
    logger.info("Successfully migrated %d posts.", successfully_uploaded)
    logger.info("Triggering Google indexing for newly migrated opinions...")
    index_opinions_with_google()

if __name__ == "__main__":
    logger.info("Starting post migration workflow")
    asyncio.run(process_workflow())
