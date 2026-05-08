import asyncio
from datetime import datetime
import json
import os
from typing import List, Union
from core import get_pdf_text, opinion_text, OPINION_LOCAL_PATH, POSTS_LOCAL_PATH, BROWSER_HEADERS, http
from agents.q_and_a_agent import get_q_and_a_agent, user_prompt as q_and_a_user_prompt, QandA
from agents.blog_post_agent import get_blog_post_agent, user_prompt as blog_post_user_prompt
from agents.case_name_agent import get_case_name_agent, user_prompt as case_name_user_prompt
from db.models.opinion_tracking import OpinionTrackingInDB
from db.connection import opinion_tracking_repo, court_opinion_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__, loglevel="DEBUG")

def opinion_text_from_court_opinion(case_key: str, page_limit: int = 15) -> Union[str, None]:
    """
    Retrieves the opinion text for a given CourtOpinionInDB entry by finding the corresponding OpinionTrackingInDB and extracting the text.
    :param case_key: The case key of the opinion
    :param page_limit: The maximum number of pages to read from the PDF (default is 15)
    :return: The extracted opinion text or None if it cannot be retrieved
    """
    tracked_opinion = opinion_tracking_repo.select_one(condition={"case_key": case_key})
    return opinion_text(tracked_opinion, page_limit=page_limit) if tracked_opinion else None

async def make_case_name(case_key: Union[str, None]) -> Union[str, None]:
    """
    Uses AI to make the case name

    This is necessary because the case name is often formatted inconsistently in the raw data, which can cause issues with citation and SEO. By using AI to generate a clean, consistent case name, we can improve the quality of our blog posts and make them more useful for attorneys.
    :param case_key: The case key of the opinion

    :return: The corrected case name or None if it cannot be generated
    """
    if not case_key:
        logger.warning("No case key provided, cannot generate case name.")
        return None
    try:
        text = opinion_text_from_court_opinion(case_key, 1)  # Get just the first page for case name generation
        if not text:
            logger.warning("No opinion text found for case %s, skipping case name correction.", case_key)
            return None
        result = await get_case_name_agent().run(user_prompt=case_name_user_prompt.format(opinion_text=text))
        corrected_name = result.output.case_name.strip()
        logger.info("Corrected case name for case %s to '%s'", case_key, corrected_name)
        return corrected_name
    except Exception as e:
        logger.error("Error correcting case name for case %s: %s", case_key, e)
        return None

async def correct_case_name_for_opinions():
    """
    Corrects the case names for all opinions that have not been corrected yet.

    This function iterates through all opinions that have not had their case names corrected, retrieves the opinion text, generates a corrected case name using AI, and updates the database record with the corrected name.
    :return: None
    """
    opinions, count = court_opinion_repo.select_many(
        {"case_name_corrected": False}
    )
    logger.info("Found %d court opinions needing case name correction", count or 0)
    for opinion in opinions:
        corrected_name = await make_case_name(opinion.case_key)
        if corrected_name:
            # Update the case name in both the court opinion and the tracked opinion if it exists
            tracked_opinion = opinion_tracking_repo.select_one(condition={"case_key": opinion.case_key})
            if tracked_opinion:
                tracked_opinion.case_name = corrected_name
                opinion_tracking_repo.update(tracked_opinion.id, tracked_opinion.model_dump(mode="json"))
            opinion.case_name = corrected_name
            opinion.case_name_corrected = True
            court_opinion_repo.update(opinion.id, opinion.model_dump(mode="json"))
    logger.info("Completed case name correction for court opinions.")

    # Now fix unmigrated tracked opinions that don't have a case name but have a case key
    tracked_opinions, tracked_count = opinion_tracking_repo.select_many(
        {"case_name": None}
    )
    logger.info("Found %d tracked opinions needing case name correction", tracked_count or 0)
    for tracked_opinion in tracked_opinions:
        corrected_name = await make_case_name(tracked_opinion.case_key)
        if corrected_name:
            tracked_opinion.case_name = corrected_name
            opinion_tracking_repo.update(tracked_opinion.id, tracked_opinion.model_dump(mode="json"))
    logger.info("Completed case name correction for tracked opinions.")

async def get_opinion_pdf_path(opinion: OpinionTrackingInDB) -> Union[str, None]:
    """
    Returns the local path to the opinion PDF, downloading it from the web only
    if it isn't already cached at OPINION_LOCAL_PATH/<case_number>.pdf.

    :param opinion: The OpinionTrackingInDB entry containing case information
    :return: The local file path of the PDF or None if it could not be obtained
    """
    local_path = os.path.join(OPINION_LOCAL_PATH, f"{opinion.case_number}.pdf")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        logger.info("Using cached PDF for case %s at %s", opinion.case_number, local_path)
        return local_path

    if not opinion.opinion_link:
        logger.warning("No opinion link for case %s, cannot download PDF.", opinion.case_number)
        return None
    try:
        response = http.get(opinion.opinion_link, headers=BROWSER_HEADERS, timeout=30)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(response.content)
        logger.info("Downloaded PDF for case %s to %s", opinion.case_number, local_path)
        return local_path
    except Exception as e:
        logger.error("Error downloading PDF for case %s: %s", opinion.case_number, e)
        logger.exception(e)
        return None

async def _process_single_q_and_a(opinion: OpinionTrackingInDB, semaphore: asyncio.Semaphore):
    """Process Q&A generation for a single opinion, respecting concurrency limit."""
    async with semaphore:
        logger.info("Generating Q&A for case %s: %s", opinion.case_number, opinion.case_name)
        text = opinion_text(opinion, page_limit=15)

        if not text:
            logger.info("No opinion text found for case %s, attempting to download PDF.", opinion.id)
            local_path = await get_opinion_pdf_path(opinion)
            if local_path:
                text = get_pdf_text(local_path, page_limit=15)
                if text:
                    logger.debug("Added opinion text from PDF to database for case %s", opinion.case_number)
                    opinion.opinion_text = text  # Cache the text in the database for future use
                    opinion_tracking_repo.update(opinion.id, opinion.model_dump(mode="json"))

        if not text:
            logger.warning("No opinion text available for case %s, skipping Q&A generation.", opinion.id)
            return
        try:
            q_and_a = await generate_q_and_a(opinion, text)
        except Exception as e:
            logger.error("Error generating Q&A for case %s: %s. Skipping.", opinion.case_number, e)
            logger.exception(e)
            return

        if q_and_a:
            logger.info("Generated Q&A for case %s, updating database record.", opinion.case_number)
            opinion.q_and_a = q_and_a
            try:
                opinion_tracking_repo.update(opinion.id, opinion.model_dump(mode="json"))
            except Exception as e:
                logger.error("Error updating DB for case %s: %s. Skipping.", opinion.case_number, e)
                logger.exception(e)

async def correct_q_and_a_for_opinions(max_concurrent: int = settings.max_concurrent_llm_calls):
    """
    Corrects the Q&A for opinions that do not have it.

    Processes up to max_concurrent opinions in parallel using asyncio.gather().

    :param max_concurrent: Maximum number of concurrent Gemini API calls (default is set in .env or settings)
    :return: None
    """
    opinions, count = opinion_tracking_repo.select_many(
        {"q_and_a": None})
    logger.info("Found %d opinions needing Q&A generation", count or len(opinions) or 0)
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [_process_single_q_and_a(opinion, semaphore) for opinion in opinions]
    await asyncio.gather(*tasks)
    logger.info("Completed Q&A generation for opinions.")

async def migrate_q_and_a_for_opinions():
    """
    Migrates Q&A from tracked opinions to court opinions that do not have it.

    This function iterates through all court opinions that do not have a Q&A generated yet,
    finds the corresponding tracked opinion, and copies the Q&A if available.

    :return: None
    """
    filter_condition: dict[str, Union[None, dict[str, None]]] = {"q_and_a": None}
    opinions, count = court_opinion_repo.select_many(filter_condition)
    logger.info("Found %d court opinions needing Q&A migration", count or len(opinions) or 0)
    for opinion in opinions:
        tracked_opinion = opinion_tracking_repo.select_one(condition={"case_key": opinion.case_key})
        if not tracked_opinion:
            logger.warning("No tracked opinion found for case key %s, skipping Q&A migration for opinion %s.", opinion.case_key, opinion.id)
            continue
        if tracked_opinion.q_and_a:
            opinion.q_and_a = tracked_opinion.q_and_a
            court_opinion_repo.update(opinion.id, opinion.model_dump(mode="json"))
    logger.info("Completed Q&A migration for court opinions.")

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

async def _process_single_blog_post(row: OpinionTrackingInDB, semaphore: asyncio.Semaphore) -> bool:
    """Process blog post and Q&A generation for a single opinion, respecting concurrency limit."""
    async with semaphore:
        _text = opinion_text(row, page_limit=15)
        if not _text:
            logger.warning("Skipping case %s due to missing opinion text.", row.case_number)
            return False

        logger.info("Generating blog post for case %s", row.case_number)
        try:
            post_body = await generate_blog_post(row, _text)
        except Exception as e:
            logger.error("Error generating blog post for case %s: %s. Skipping.", row.case_number, e)
            return False
        if not post_body:
            logger.warning("Skipping case %s due to failure in blog post generation.", row.case_number)
            return False

        logger.info("Generating Q&A for case %s", row.case_number)
        try:
            q_and_a = await generate_q_and_a(row, _text)
        except Exception as e:
            logger.error("Error generating Q&A for case %s: %s. Continuing without Q&A.", row.case_number, e)
            q_and_a = []

        row.body = post_body
        row.q_and_a = q_and_a  # Pydantic will serialize automatically

        filename = f"draft_{row.case_number}.json"
        full_path = os.path.join(POSTS_LOCAL_PATH, filename)
        logger.info("Saving draft post to %s", full_path)
        with open(full_path, 'w') as f:
            draft = row.model_dump(mode="json")
            draft["opinion_text"] = _text  # Include the opinion text in the saved draft for reference
            f.write(json.dumps(draft))

        try:
            opinion_tracking_repo.update(row.id, row.model_dump(mode="json"))
            logger.info("Updated database record for case %s", row.case_number)
        except Exception as e:
            logger.error("Error updating DB for case %s: %s. Skipping.", row.case_number, e)
            return False

        return True

async def generate_blog_posts(max_concurrent: int = settings.max_concurrent_llm_calls):
    """
    Generates blog posts for all opinions that are pending blog generation.

    Processes up to max_concurrent opinions in parallel using asyncio.gather().

    :param max_concurrent: Maximum number of concurrent Gemini API calls (default is set in .env or settings)
    :return: A tuple containing the path where posts are saved and the count of generated posts
    :rtype: Tuple[str, int]
    """
    try:
        records, _ = opinion_tracking_repo.select_many(condition={"status": "pending-blog", "has_substance": True})  # type: ignore
        records: List[OpinionTrackingInDB]
        logger.info("Found %d opinions pending blog generation", len(records))
        semaphore = asyncio.Semaphore(max_concurrent)
        results = await asyncio.gather(*[_process_single_blog_post(row, semaphore) for row in records])
        post_count = sum(1 for r in results if r)
        return POSTS_LOCAL_PATH, post_count
    except Exception as e:
        logger.error("Error generating blog posts: %s", e)
        logger.exception(e)
        return POSTS_LOCAL_PATH, 0

async def run_blogger_bot():
    # Generate the blog posts
    logger.info("Generating draft blog posts")
    saved_as, count = await generate_blog_posts()
    logger.info("Drafted %d blog posts, saved to %s", count, saved_as)

if __name__ == "__main__":
    logger.info("Starting blogger bot")
    asyncio.run(run_blogger_bot())
