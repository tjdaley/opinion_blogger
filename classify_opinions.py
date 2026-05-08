"""
classify_opinions.py - LLM classification stage for freshly-scraped opinions.

Reads rows at status='pending-analysis' (inserted by the scrapers with raw
metadata and opinion_text, but no LLM-derived fields), runs
`analyze_with_full_text` to classify and extract metadata, then transitions
each row to either 'pending-blog' (family law) or 'pending-family-review'
(non-family, to be checked for crossover relevance).

On LLM failure the row stays at 'pending-analysis' so the next run retries.
After the first-pass classification, this stage kicks off the existing
`review_non_family_cases` crossover pass.
"""
import asyncio
from typing import List

from core import analyze_with_full_text, review_non_family_cases
from db.connection import opinion_tracking_repo
from db.models.opinion_tracking import OpinionTrackingInDB
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)


async def _classify_one(row: OpinionTrackingInDB, semaphore: asyncio.Semaphore) -> bool:
    """Classify a single row. Returns True if transitioned, False if left at pending-analysis."""
    async with semaphore:
        if not row.opinion_text:
            logger.warning("Case %s has no opinion_text; leaving at pending-analysis.", row.case_number)
            return False

        try:
            analysis = await analyze_with_full_text(row.case_name or row.headline, row.opinion_text)
        except Exception as e:
            logger.error("LLM classification failed for case %s: %s. Leaving at pending-analysis.", row.case_number, e)
            return False

        row.is_family_law = analysis.family_law
        if analysis.headline:
            row.headline = analysis.headline
        if analysis.legal_issue:
            row.legal_issue = analysis.legal_issue
        if analysis.holding:
            row.holding = analysis.holding
        if analysis.case_name:
            row.case_name = analysis.case_name
        if analysis.lower_court_name:
            row.lower_court_name = analysis.lower_court_name
        row.seo_title = None  # SEO title will be generated later in the pipeline, so we clear it here in case it was populated by a previous run
        row.seo_focus_kw = analysis.seo_focus_kw
        row.meta_description = analysis.meta_description
        row.has_substance = analysis.has_substance
        if not row.has_substance:
            logger.info("Case %s classified as having no substance; setting status to 'no-substance'", row.case_number)
            row.status = "no-substance"
        else:
            row.status = "pending-blog" if analysis.family_law else "pending-family-review"

        try:
            opinion_tracking_repo.update(row.id, row.model_dump(mode="json"))
            logger.info("Classified %s -> %s (family_law=%s)", row.case_number, row.status, row.is_family_law)
            return True
        except Exception as e:
            logger.error("DB update failed for case %s after classification: %s", row.case_number, e)
            return False


async def classify_pending(max_concurrent: int = settings.max_concurrent_llm_calls):
    """Classify all rows at status='pending-analysis', then run the crossover review."""
    records, _ = opinion_tracking_repo.select_many(condition={"status": "pending-analysis"})  # type: ignore
    records: List[OpinionTrackingInDB]
    logger.info("Found %d opinions pending classification", len(records))

    if records:
        semaphore = asyncio.Semaphore(max_concurrent)
        await asyncio.gather(*[_classify_one(row, semaphore) for row in records])

    logger.info("Running crossover review for non-family cases")
    await review_non_family_cases()


if __name__ == "__main__":
    logger.info("Starting classifier")
    asyncio.run(classify_pending())
