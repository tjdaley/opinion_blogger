import json
from typing import List, Union
import requests
from markdownify import markdownify as md
from openai import OpenAI
from util.settings import settings
from db.models.legal_subject import LegalSubjectInDB
from db.models.court_opinion import CourtOpinion
from db.supabasemanager import SupabaseManager
from db.repositories.legal_subject import LegalSubjectRepository
from db.repositories.court_opinion import OpinionRepository

# --- Database Setup ---
DB_MANAGER = SupabaseManager()
OPINIONS = OpinionRepository(DB_MANAGER)
LEGAL_SUBJECTS = LegalSubjectRepository(DB_MANAGER)

# --- Configuration ---
WP_URL = settings.wp_base_url
WP_USER = settings.wp_username
WP_APP_PASSWORD = settings.wp_app_password

ai_client = OpenAI(api_key=settings.openai_api_key)

def get_tag_id(tag_slug: str) -> Union[int, None]:
    """Fetch the ID of a tag given its slug."""
    response = requests.get(f"{WP_URL}/tags?slug={tag_slug}", auth=(WP_USER, WP_APP_PASSWORD))
    tags = response.json()
    if tags:
        return tags[0]['id']
    return None

def get_posts_to_process(tag_slug: str) -> List[dict[str, str]]:
    """Fetch posts with specific tag and 'publish' status."""
    # Find the tag ID
    tag_id = get_tag_id(tag_slug) or 0

    # Get posts with that tag
    params: dict[str, Union[str, int]] = {'status': 'publish', 'tags': tag_id, 'context': 'edit'}
    posts_resp = requests.get(f"{WP_URL}/posts", params=params, auth=(WP_USER, WP_APP_PASSWORD))
    return posts_resp.json()

def clean_text(text: str) -> str:
    """
    Clean text by removing excessive whitespace and removing invalid unicode characters.
    """
    # Remove excessive whitespace
    response = ' '.join(text.split())

    # Remove invalid unicode characters
    response = response.encode('utf-8', 'ignore').decode('utf-8', 'ignore')

    return response

def process_workflow():
    categories_in_db: List[LegalSubjectInDB]
    categories_in_db, _ = LEGAL_SUBJECTS.select_many({})  # type: ignore
    defined_categories = [cat.id for cat in categories_in_db]
    DEFINED_CATEGORIES = ", ".join(defined_categories)
    tag_to_publish = settings.wp_post_tag
    tag_id_to_publish = get_tag_id(tag_to_publish)
    tag_to_mark_error = settings.wp_error_tag
    tag_id_to_mark_error = get_tag_id(tag_to_mark_error)
    tag_to_mark_success = settings.wp_success_tag
    tag_id_to_mark_success = get_tag_id(tag_to_mark_success)
    posts = get_posts_to_process(tag_to_publish)
    
    for post in posts:
        try:
            # 0. See if we should skip due to prior error
            current_tags: list[int] = post['tags']  # type: ignore
            if tag_id_to_mark_error and tag_id_to_mark_error in current_tags:
                print(f"Skipping post {post.get('id')} due to prior error tag.")
                continue

            # 1. Convert WP HTML to Clean Markdown
            raw_html = post['content']['raw']  # type: ignore
            # strip_tags=True removes things like <div> or <span> while keeping <a>, <b>, etc.
            markdown_body = md(raw_html, strip=['script', 'style'], heading_style="ATX")

            # 2. AI Transformation
            # We pass the markdown to the AI so it can better identify structures
            headline = post['title']['rendered']  # type: ignore
            
            prompt = f"""
            Act as a legal editor for JDBOT. Convert this blog post into the following JSON:
            Keys: case_name, court, opinion_date, brief_summary, litigation_takeaway, slug, category, citation, opinion_link.
            
            Available Categories: {DEFINED_CATEGORIES}
            
            Important: The 'blog_body' must be the following Markdown content exactly.
            
            Headline: {headline}
            Content: {markdown_body}
            """

            response = ai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            structured_data = json.loads(response.choices[0].message.content)  # type: ignore

            # 3. Save to Supabase
            opinion = CourtOpinion(
                case_name=clean_text(structured_data['case_name']),
                court=clean_text(structured_data['court']),
                date=clean_text(structured_data['opinion_date']),
                summary=clean_text(structured_data['brief_summary']),
                litigation_takeaway=clean_text(structured_data['litigation_takeaway']),
                slug=clean_text(structured_data['slug']),
                category=clean_text(structured_data['category']),
                citation=clean_text(structured_data['citation']),
                opinion_link=clean_text(structured_data['opinion_link']),
                blog_post=clean_text(markdown_body),
                needs_review=True
            )

            try:
                OPINIONS.insert(opinion.model_dump(mode="json"))
                print(f"Saved {structured_data['case_name']} to Supabase.")

                # 4. Remove the tag from WordPress so it doesn't process again
                current_tags: list[int] = post['tags']  # type: ignore
                new_tags = [t for t in current_tags if t != tag_id_to_publish]
                if tag_id_to_mark_success and tag_id_to_mark_success not in new_tags:
                    new_tags.append(tag_id_to_mark_success)
                
                requests.post(f"{WP_URL}/posts/{post['id']}", 
                            json={'tags': new_tags}, 
                            auth=(WP_USER, WP_APP_PASSWORD))
            except Exception as db_e:
                print(f"DB Error on post {post.get('id')}: {db_e}")
                # Tag the post with error tag
                current_tags: list[int] = post['tags']  # type: ignore
                if tag_id_to_mark_error and tag_id_to_mark_error not in current_tags:
                    current_tags.append(tag_id_to_mark_error)
                requests.post(f"{WP_URL}/posts/{post['id']}", 
                            json={'tags': current_tags}, 
                            auth=(WP_USER, WP_APP_PASSWORD))

        except Exception as e:
            print(f"Error on post {post.get('id')}: {e}")

if __name__ == "__main__":
    process_workflow()