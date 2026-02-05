import asyncio
from datetime import datetime
import os
from typing import List, Union
import fitz  # pyright: ignore[reportMissingTypeStubs] # PyMuPDF
from util.settings import settings
from agents.q_and_a_agent import get_q_and_a_agent, user_prompt as q_and_a_user_prompt, QandA
from agents.blog_post_agent import get_blog_post_agent, user_prompt as blog_post_user_prompt
from db.models.opinion_tracking import OpinionTrackingInDB
from db.repositories.opinion_tracking import OpinionTrackingRepository
from db.supabasemanager import SupabaseManager
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

# --- CONFIGURATION ---
OPINION_LOCAL_PATH = settings.opinion_local_path
POSTS_LOCAL_PATH = settings.posts_local_path
MAX_OPINION_SIZE = settings.max_opinion_size

# --- DB SETUP ---
manager = SupabaseManager()
opinion_repo = OpinionTrackingRepository(manager)

# Prepare output paths
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

def get_pdf_text(filepath: str) -> str:
    """Extracts the first MAX_OPINION_SIZE characters from the PDF for AI analysis."""
    text = ""
    try:
        with fitz.open(filepath) as doc:
            # We usually only need the first few pages for the summary/holding
            for page in doc[:5]:
                text += page.get_text()  # type: ignore
    except Exception as e:
        logger.error("Error reading PDF %s: %s", filepath, e)
    return text[:MAX_OPINION_SIZE]  # type: ignore

def opinion_text(row: OpinionTrackingInDB) -> Union[str, None]:
    # We fetch the PDF text we already downloaded
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row.case_number}.pdf")
    _text = get_pdf_text(pdf_path) if os.path.exists(pdf_path) else ""
    return _text

async def generate_q_and_a(case_data: OpinionTrackingInDB, opinion_text: str) -> List[QandA]:
    """
    Docstring for generate_q_and_a

    :param case_data: Description
    :type case_data: OpinionTrackingInDB
    :param opinion_text: Description
    :type opinion_text: str
    :return: Description
    :rtype: List[QandA]
    """
    user_prompt = q_and_a_user_prompt.format(opinion_text=opinion_text)
    result = await get_q_and_a_agent().run(user_prompt=user_prompt)
    return result.output

async def generate_blog_post(case_data: OpinionTrackingInDB, opinion_text: str) -> Union[str, None]:
    """
    Generates a professional blog post designed for attorney citation.
    """
    date_object = datetime.strptime(str(case_data.opinion_date), "%Y-%m-%d")
    opinion_date = date_object.strftime("%B %d, %Y")

    if not case_data.is_family_law:
        additional_instruction = """
    9. CROSSOVER
       (a) Fixed Header Text: "Family Law Crossover"
       (b) Content: Explain how this civil ruling can be weaponized in a Texas divorce or custody case?
       (c) Content Style: Paragraph
       (d) Header Style: H2
"""
    else:
        additional_instruction = ""

    prompt = blog_post_user_prompt.format(
        case_number=case_data.case_number,
        headline=case_data.headline,
        legal_issue=case_data.legal_issue,
        holding=case_data.holding,
        opinion_text=opinion_text,
        case_name=case_data.case_name,
        opinion_date=opinion_date,
        lower_court_name=case_data.lower_court_name,
        opinion_link=case_data.opinion_link,
        additional_instruction=additional_instruction
    )

    try:
        result = await get_blog_post_agent().run(user_prompt=prompt)
    except Exception as e:
        logger.error("Error generating blog post for case %s: %s", case_data.case_number, e)
        logger.exception(e)
        return None
    return result.output

async def generate_blog_posts():
    post_count = 0

    try:
        records, _ = opinion_repo.select_many(condition={"status": "pending-blog"})  # type: ignore
        records: List[OpinionTrackingInDB]
        for row in records:
            _text = opinion_text(row)
            if not _text:
                logger.warning("Skipping case %s due to missing opinion text.", row.case_number)
                continue

            logger.info("Generating blog post for case %s", row.case_number)
            post_body = await generate_blog_post(row, _text)
            if not post_body:
                logger.warning("Skipping case %s due to failure in blog post generation.", row.case_number)
                continue

            logger.info("Generating Q&A for case %s", row.case_number)
            q_and_a = await generate_q_and_a(row, _text)
            if post_body:
                row.body = post_body
                row.q_and_a = q_and_a  # Pydantic will serialize automatically
                post_count += 1

                filename = f"draft_{row.case_number}.json"
                full_path = os.path.join(POSTS_LOCAL_PATH, filename)
                logger.info("Saving draft post to %s", full_path)
                with open(full_path, 'w') as f:
                    f.write(row.model_dump_json())

                logger.info("Updated database record for case %s", row.case_number)
                opinion_repo.update(row.id, row.model_dump(mode="json"))

        return POSTS_LOCAL_PATH, post_count
    except Exception as e:
        logger.error("Error generating blog posts: %s", e)
        logger.exception(e)
        return POSTS_LOCAL_PATH, post_count

async def run_blogger_bot():
    # Generate the blog posts
    logger.info("Generating draft blog posts")
    saved_as, count = await generate_blog_posts()
    logger.info("Drafted %d blog posts, saved to %s", count, saved_as)

if __name__ == "__main__":
    logger.info("Starting blogger bot")
    asyncio.run(run_blogger_bot())
