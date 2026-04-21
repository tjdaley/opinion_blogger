"""
wp_uploader - A script to upload case law updates to WordPress using the REST API.
"""
from typing import List, Union
import requests
from requests.auth import HTTPBasicAuth
import markdown
from util.settings import settings
from db.models.opinion_tracking import OpinionTrackingInDB
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

# --- CONFIGURATION ---
WP_BASE_URL = settings.wp_base_url
WP_USERNAME = settings.wp_username
WP_APP_PASSWORD = settings.wp_app_password
AUTHOR_ID = int(settings.author_id)
SCOTX_CATEGORY_IDS = settings.scotx_category_ids
SCOTX_TAG_IDS = settings.scotx_tag_ids
SCOTX_MEDIA_ID = int(settings.scotx_media_id)
COATX_CATEGORY_IDS = settings.coatx_category_ids
COATX_TAG_IDS = settings.coatx_tag_ids
COATX_MEDIA_ID = int(settings.coatx_media_id)

def get_tag_id(tag_slug: str) -> Union[int, None]:
    """Fetch the ID of a tag given its slug."""
    response = requests.get(f"{WP_BASE_URL}/tags?slug={tag_slug}", auth=(WP_USERNAME, WP_APP_PASSWORD))
    tags = response.json()
    if tags:
        return tags[0]['id']
    return None

def trash_empty_posts(status: str = "draft") -> dict[str, int]:
    """
    Move any empty drafts to trash to avoid clutter.
    
    This happens when the scraper fails to create a draft--usually and LLM problem, such as
    a rate limit issue. If we trash the empty blog posts, we can rerun the scraper job
    and instead of re-getting the opinions, the scraper job will pick up at the last failed
    step, which is usually the blog post creation step.

    Returns:

        A dictionary with the count of drafts found and trashed.
    """
    auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    response = requests.get(f"{WP_BASE_URL}/posts?status={status}", auth=auth)
    posts = response.json()
    post_count = len(posts)
    logger.info("Found %d %s posts in WordPress", post_count, status)
    deleted_count = 0
    while posts:
        for post in posts:
            if not len(post['content']['rendered'].strip()) > 250:  # Arbitrary threshold for "empty"
                logger.info("Trashing empty draft: %s (ID: %d)", post['title']['rendered'], post['id'])
                requests.delete(f"{WP_BASE_URL}/posts/{post['id']}?force=true", auth=auth)
                deleted_count += 1
        response = requests.get(f"{WP_BASE_URL}/posts?status={status}", auth=auth)
        posts = response.json()
        post_count += len(posts)
        
    logger.info("Trashed %d empty %s posts.", deleted_count, status)

    return {"found": post_count, "trashed": deleted_count}


def upload_to_wordpress(post: OpinionTrackingInDB) -> bool:
    auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

    html_content = markdown.markdown(
        f"{post.body}\n\n~~{post.case_key}~~",  # type: ignore
        extensions=['extra', 'nl2br', 'sane_lists']
    )

    # Prepare the payload
    # Note: Yoast SEO fields are often handled via the 'meta' key
    tags = SCOTX_TAG_IDS if post.court == "SCOTX" else COATX_TAG_IDS
    tags = list(tags)  # Convert tuple to list for mutability
    tags.append(get_tag_id(settings.wp_post_tag))  # type: ignore
    payload = {  # type: ignore
        "title": post.headline,
        "content": html_content,
        "status": "draft",
        "author": AUTHOR_ID,
        "categories": SCOTX_CATEGORY_IDS if post.court == "SCOTX" else COATX_CATEGORY_IDS,
        "tags": tags,
        "comment_status": "closed",
        "featured_media": SCOTX_MEDIA_ID if post.court == "SCOTX" else COATX_MEDIA_ID,
        "meta": {
            "_yoast_wpseo_title": post.seo_title or post.headline,  # type: ignore
            "_yoast_wpseo_metadesc": (post.meta_description or post.legal_issue)[:156], # type: ignore
            "_yoast_wpseo_focuskw": post.seo_focus_kw or "Texas Family Law Case Update",  # type: ignore
            "_yoast_wpseo_author": "Thomas J. Daley",
            "case_id": post.case_key or ''
        }
    }

    response = requests.post(f"{WP_BASE_URL}/posts", json=payload, auth=auth)  # type: ignore

    if response.status_code == 201:
        logger.info("{green}{bold}Success: Posted %s as Draft.", post.case_number)
        return True
    else:
        logger.error("{red}{bold}Error posting %s: %s", post.case_number, response.text)
        return False

def run_uploader():
    posts, _ = opinion_tracking_repo.select_many(condition={"status": "pending-blog"})  # type: ignore

    successfully_uploaded = 0
    if not posts:
        logger.info("{purple}No pending drafts found.")
        return

    posts: List[OpinionTrackingInDB]
    for post in posts:
        success = upload_to_wordpress(post)
        if success:
            post.status = 'blog-drafted'
            opinion_tracking_repo.update(post.id, post.model_dump(mode="json"))
            successfully_uploaded += 1
        else:
            logger.info("Skipping %s - Upload failed. Status is %s", post.case_number, post.status)

    logger.info("Successfully uploaded %d posts.", successfully_uploaded)

if __name__ == "__main__":
    logger.info("Starting WordPress uploader bot")
    run_uploader()
    logger.info("WordPress uploader bot finished")
