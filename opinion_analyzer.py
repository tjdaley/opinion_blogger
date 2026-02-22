import asyncio
from datetime import datetime
import json
import os
from typing import List, Union
import fitz  # pyright: ignore[reportMissingTypeStubs] # PyMuPDF
import requests
from util.settings import settings
from agents.q_and_a_agent import get_q_and_a_agent, user_prompt as q_and_a_user_prompt, QandA
from agents.blog_post_agent import get_blog_post_agent, user_prompt as blog_post_user_prompt
from agents.case_name_agent import get_case_name_agent, user_prompt as case_name_user_prompt
from db.models.court_opinion import CourtOpinionInDB
from db.models.opinion_tracking import OpinionTrackingInDB
from db.repositories.court_opinion import OpinionRepository
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
court_opinion_repo = OpinionRepository(manager)

# Prepare output paths
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

def get_pdf_text(filepath: str, page_limit: int = 15) -> str:
    """
    Extracts the first MAX_OPINION_SIZE characters from the PDF for AI analysis.

    :param filepath: Path to the PDF file
    :param page_limit: Maximum number of pages to read from the PDF (default is 15)
    """
    text = ""
    try:
        with fitz.open(filepath) as doc:
            # We usually only need the first few pages for the summary/holding
            for page in doc[:page_limit]:
                text += page.get_text()  # type: ignore
    except Exception as e:
        logger.error("Error reading PDF %s: %s", filepath, e)
    return text[:MAX_OPINION_SIZE]  # type: ignore

def opinion_text(row: OpinionTrackingInDB, page_limit: int = 15) -> Union[str, None]:
    """
    Retrieves the opinion text for a given case, either from local storage or by downloading the PDF.
    
    :param row: The opinion tracking database row containing case information
    :param page_limit: The maximum number of pages to read from the PDF (default is 15)
    :return: The extracted opinion text or None if it cannot be retrieved
    """
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row.case_number}.pdf")
    _text = get_pdf_text(pdf_path, page_limit=page_limit) if os.path.exists(pdf_path) else ""
    return _text

def opinion_text_from_court_opinion(opinion: CourtOpinionInDB, page_limit: int = 15) -> Union[str, None]:
    """
    Retrieves the opinion text for a given CourtOpinionInDB entry by finding the corresponding OpinionTrackingInDB and extracting the text.
    :param opinion: The CourtOpinionInDB entry containing case information
    :param page_limit: The maximum number of pages to read from the PDF (default is 15)
    :return: The extracted opinion text or None if it cannot be retrieved
    """
    tracked_opinion = opinion_repo.select_one(condition={"case_key": opinion.case_key})
    return opinion_text(tracked_opinion, page_limit=page_limit) if tracked_opinion else None

async def make_case_name(case_data: CourtOpinionInDB) -> Union[str, None]:
    """
    Uses AI to make the case name

    This is necessary because the case name is often formatted inconsistently in the raw data, which can cause issues with citation and SEO. By using AI to generate a clean, consistent case name, we can improve the quality of our blog posts and make them more useful for attorneys.
    :param case_data: The CourtOpinionInDB entry containing case information
    :return: The corrected case name or None if it cannot be generated
    """
    try:
        text = opinion_text_from_court_opinion(case_data, 1)  # Get just the first page for case name generation
        if not text:
            logger.warning("No opinion text found for case %s, skipping case name correction.", case_data.id)
            return None
        result = await get_case_name_agent().run(user_prompt=case_name_user_prompt.format(opinion_text=text))
        corrected_name = result.output.case_name.strip()
        logger.info("Corrected case name from '%s' to '%s'", case_data.case_name, corrected_name)
        return corrected_name
    except Exception as e:
        logger.error("Error correcting case name '%s': %s", case_data.case_name, e)
        return None
    
async def correct_case_name_for_opinions():
    opinions, _ = court_opinion_repo.select_many(
        {"case_name_corrected": False})
    for opinion in opinions:
        corrected_name = await make_case_name(opinion)
        if corrected_name:
            opinion.case_name = corrected_name
            opinion.case_name_corrected = True
            court_opinion_repo.update(opinion.id, opinion.model_dump(mode="json"))

async def download_opinion_pdf(opinion: OpinionTrackingInDB) -> Union[str, None]:
    """
    Downloads the opinion PDF to local storage for AI analysis.
    Returns the local file path or None if download failed.

    :param opinion: The OpinionTrackingInDB entry containing case information
    :return: The local file path of the downloaded PDF or None if download failed
    """
    if not opinion.opinion_link:
        logger.warning("No opinion link for case %s, cannot download PDF.", opinion.case_number)
        return None
    try:
        response = requests.get(opinion.opinion_link)
        response.raise_for_status()
        local_path = os.path.join(OPINION_LOCAL_PATH, f"{opinion.case_number}.pdf")
        with open(local_path, 'wb') as f:
            f.write(response.content)
        logger.info("Downloaded PDF for case %s to %s", opinion.case_number, local_path)
        return local_path
    except Exception as e:
        logger.error("Error downloading PDF for case %s: %s", opinion.case_number, e)
        return None

async def correct_q_and_a_for_opinions():
    """
    Corrects the Q&A for opinions that do not have it.

    This function iterates through all opinions that do not have a Q&A generated yet,
    retrieves the opinion text, and generates the Q&A using AI.

    :return: None
    """
    opinions, _ = opinion_repo.select_many(
        {"q_and_a": None})
    for opinion in opinions:
        text = opinion_text(opinion)
        if not text:
            logger.info("No opinion text found for case %s, attempting to download PDF.", opinion.id)
            local_path = await download_opinion_pdf(opinion)
            if local_path:
                text = get_pdf_text(local_path)
        if not text:
            logger.warning("No opinion text available for case %s, skipping Q&A generation.", opinion.id)
            continue
        q_and_a = await generate_q_and_a(opinion, text)
        if q_and_a:
            opinion.q_and_a = q_and_a
            opinion_repo.update(opinion.id, opinion.model_dump(mode="json"))

async def migrate_q_and_a_for_opinions():
    """
    Migrates Q&A from tracked opinions to court opinions that do not have it.

    This function iterates through all court opinions that do not have a Q&A generated yet,
    finds the corresponding tracked opinion, and copies the Q&A if available.

    :return: None
    """
    opinions, _ = court_opinion_repo.select_many(
        {"q_and_a": None, "case_key": {"$ne": None}})
    for opinion in opinions:
        tracked_opinion = opinion_repo.select_one(condition={"case_key": opinion.case_key})
        if not tracked_opinion:
            logger.warning("No tracked opinion found for case key %s, skipping Q&A migration for opinion %s.", opinion.case_key, opinion.id)
            continue
        if tracked_opinion.q_and_a:
            opinion.q_and_a = tracked_opinion.q_and_a
            court_opinion_repo.update(opinion.id, opinion.model_dump(mode="json"))

async def generate_q_and_a(case_data: OpinionTrackingInDB, opinion_text: str) -> List[QandA]:
    """
    Generate Questions and Answers based on the opinion text to help attorneys quickly
    understand the case. The questions are designed to be practical and focused on
    litigation strategy, not just legal analysis..

    :param case_data: The OpinionTrackingInDB entry containing case information
    :type case_data: OpinionTrackingInDB
    :param opinion_text: The text of the opinion to analyze for Q&A generation
    :type opinion_text: str
    :return: A list of QandA objects generated from the opinion text
    :rtype: List[QandA]
    """
    user_prompt = q_and_a_user_prompt.format(opinion_text=opinion_text)
    result = await get_q_and_a_agent().run(user_prompt=user_prompt)
    return result.output

async def generate_blog_post(case_data: OpinionTrackingInDB, opinion_text: str) -> Union[str, None]:
    """
    Generates a professional blog post designed for attorney citation.

    The blog post includes a summary of the case, the holding, and practical takeaways for litigation strategy. If the case is not a family law case, it also includes a section on how the ruling could be used in a family law context.

    :param case_data: The OpinionTrackingInDB entry containing case information
    :param opinion_text: The text of the opinion to analyze for blog post generation
    :return: The generated blog post as a string, or None if generation fails
    :rtype: Union[str, None]
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
    """
    Generates blog posts for all opinions that are pending blog generation.

    This function retrieves all opinions that are marked as pending blog generation, extracts the opinion text, generates a blog post using AI, and saves the generated post to local storage. It also updates the database record for each opinion with the generated blog post content.
    :return: A tuple containing the path where posts are saved and the count of generated posts
    :rtype: Tuple[str, int]
    """
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
                    draft = row.model_dump(mode="json")
                    draft["opinion_text"] = _text  # Include the opinion text in the saved draft for reference
                    f.write(json.dumps(draft))

                logger.info("Updated database record for case %s", row.case_number)
                opinion_repo.update(row.id, row.model_dump(mode="json"))

        return POSTS_LOCAL_PATH, post_count
    except Exception as e:
        logger.error("Error generating blog posts: %s", e)
        logger.exception(e)
        return POSTS_LOCAL_PATH, post_count

async def run_blogger_bot():
    # Generate the blog posts
    #logger.info("Generating draft blog posts")
    #saved_as, count = await generate_blog_posts()
    #logger.info("Drafted %d blog posts, saved to %s", count, saved_as)
    #logger.info("Correcting case names for opinions")
    #await correct_case_name_for_opinions()
    logger.info("Generating Q&A for opinions")
    await correct_q_and_a_for_opinions()
    logger.info("Migrating Q&A for opinions")
    await migrate_q_and_a_for_opinions()

if __name__ == "__main__":
    logger.info("Starting blogger bot")
    asyncio.run(run_blogger_bot())
