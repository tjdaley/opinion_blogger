"""
seo_title_generator.py - Generate SEO titles for CourtOpinions and persist them.

Provides:
  - generate_and_save_seo_title(opinion): single-opinion helper suitable for
    inlining into promote_to_branding.
  - backfill_seo_titles(limit=None): bulk backfill of any opinions whose
    seo_title is NULL.
"""
import asyncio
import json
from typing import Any, Optional

from agents.seo_title_agent import get_seo_title_agent, user_prompt as seo_title_user_prompt
from db.connection import opinion_tracking_repo
from db.models.opinion_tracking import OpinionTrackingInDB
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

# Fields the seo_title_agent system prompt expects in the case_information JSON.
PROMPT_FIELDS = (
    "case_name",
    "court",
    "date",
    "summary",
    "litigation_takeaway",
    "citation",
    "category",
    "blog_post",
    "q_and_a",
    "lower_court_name",
)


def _build_case_information(opinion: OpinionTrackingInDB) -> dict[str, Any]:
    """Build the case_information dict the seo_title_agent system prompt expects."""
    dumped = opinion.model_dump(mode="json")
    return {field: dumped.get(field) for field in PROMPT_FIELDS}


async def generate_and_save_seo_title(opinion: OpinionTrackingInDB) -> bool:
    """Generate an SEO title for one opinion and persist it to the DB.

    Mutates `opinion.seo_title` in place on success so callers can keep using
    the same object. Returns True on success, False on any failure (logged).
    """
    if opinion.status == "rejected":
        logger.info("Opinion is rejected; skipping SEO title generation for case_key=%s", opinion.case_key)
        return False

    case_key = opinion.case_key or ""
    try:
        case_info = _build_case_information(opinion)
        prompt = seo_title_user_prompt.format(
            json_string=json.dumps(case_info, default=str)
        )
        result = await get_seo_title_agent().run(user_prompt=prompt)
        title = (result.output or "").strip()
        if not title:
            logger.warning("Empty SEO title for case_key=%s", case_key)
            return False

        opinion.seo_title = title
        opinion_tracking_repo.update(opinion.id, opinion.model_dump(mode="json"))
        logger.info("Saved SEO title for case_key=%s -> %s", case_key, title)
        return True
    except Exception:
        logger.exception("SEO title generation failed for case_key=%s", case_key)
        return False


async def _process_one(opinion: OpinionTrackingInDB, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        return await generate_and_save_seo_title(opinion)


BATCH_SIZE = 500


async def backfill_seo_titles(limit: Optional[int] = None) -> None:
    """Generate and save SEO titles for every CourtOpinion whose seo_title is NULL.

    Fetches and processes in batches of `BATCH_SIZE`, looping until no further
    fresh records remain. Records that fail are tracked in-process and excluded
    from subsequent batch fetches so a persistent failure can't infinite-loop
    the run (re-running the command will retry them on a fresh process).

    :param limit: Optional cap on how many opinions to attempt this run. None = all.
    """
    logger.info(
        "Backfilling SEO titles: vendor=%s model=%s limit=%s batch_size=%d",
        settings.seo_title_vendor, settings.seo_title_model, limit, BATCH_SIZE,
    )

    semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)
    attempted: set[int] = set()
    total_attempted = 0
    total_succeeded = 0

    while limit is None or total_attempted < limit:
        desired = BATCH_SIZE
        if limit is not None:
            desired = min(BATCH_SIZE, limit - total_attempted)

        batch, remaining_in_db = opinion_tracking_repo.select_many(
            condition={"seo_title": None},
            sort_by="opinion_date",
            sort_direction="desc",
            start=0,
            end=desired - 1,
        )
        fresh = [op for op in batch if op.id not in attempted]
        if not fresh:
            logger.info("No fresh records remain; backfill complete.")
            break

        logger.info(
            "Processing batch of %d (DB has %d rows still IS NULL)",
            len(fresh), remaining_in_db,
        )
        attempted.update(op.id for op in fresh)

        results = await asyncio.gather(
            *(_process_one(op, semaphore) for op in fresh)
        )
        succeeded = sum(1 for r in results if r)
        total_attempted += len(results)
        total_succeeded += succeeded
        logger.info(
            "Batch done: %d/%d succeeded (run totals: %d/%d)",
            succeeded, len(results), total_succeeded, total_attempted,
        )

    logger.info("SEO title backfill done: %d/%d succeeded", total_succeeded, total_attempted)
