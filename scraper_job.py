"""
scraper_job.py - CLI entry point for the opinion blogger pipeline.

Usage:
    python scraper_job.py                  # Run full pipeline (default: all)
    python scraper_job.py all              # Run full pipeline
    python scraper_job.py scrape           # Run all scrapers (SCOTX + COA)
    python scraper_job.py scrape scotx     # Run only SCOTX scraper
    python scraper_job.py scrape coa       # Run only COA scraper
    python scraper_job.py classify         # Run LLM classification on pending-analysis rows
    python scraper_job.py analyze          # Run opinion analyzer / blog generator
    python scraper_job.py upload           # Run WordPress uploader
    python scraper_job.py repair           # Run repair functions
"""

import argparse
import asyncio
import notifier as notifier
from core import ensure_directories
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)


async def cmd_scrape(target: str = "all"):
    """Run scraper(s) based on target."""
    if target in ("all", "scotx"):
        from txcourts_scotx_scraper import scrape_tx_courts
        logger.info("Running SCOTX scraper")
        await scrape_tx_courts()

    if target in ("all", "coa"):
        from tx_coa_scraper import scrape_coa_opinions
        logger.info("Running COA scraper")
        await scrape_coa_opinions()

async def cmd_classify():
    """Classify pending-analysis opinions (family-law check + metadata extraction)."""
    from classify_opinions import classify_pending
    logger.info("Running opinion classifier")
    await classify_pending()


async def cmd_analyze():
    """Run the opinion analyzer and blog post generator."""
    from opinion_analyzer import run_blogger_bot
    logger.info("Running opinion analyzer")
    await run_blogger_bot()


def cmd_upload():
    """Run the WordPress uploader."""
    from wp_uploader import run_uploader
    logger.info("Running WordPress uploader")
    run_uploader()

async def cmd_promote_to_branding():
    """Run the proote to branding migration."""
    from post_migrator import process_workflow
    logger.info("Running promote to branding migration")
    await process_workflow()


async def cmd_repair_case_names():
    """Run repair/correction functions for case names."""
    from opinion_analyzer import correct_case_name_for_opinions
    logger.info("Running repair: correct case names")
    await correct_case_name_for_opinions()

async def cmd_repair_q_and_a():
    """Run repair/correction functions for Q&A."""
    from opinion_analyzer import correct_q_and_a_for_opinions, migrate_q_and_a_for_opinions
    logger.info("Running repair: correct Q&A")
    await correct_q_and_a_for_opinions()
    logger.info("Running repair: migrate Q&A")
    await migrate_q_and_a_for_opinions()

def cmd_trash_empty_drafts():
    """Trash any empty drafts in WordPress to avoid clutter."""
    from wp_uploader import trash_empty_posts
    logger.info("Trashing empty drafts in WordPress")
    result = trash_empty_posts()
    logger.info("Trashed %d empty drafts out of %d found.", result["trashed"], result["found"])

def cmd_trash_empty_posts():
    """Trash any empty posts in WordPress to avoid clutter."""
    from wp_uploader import trash_empty_posts
    logger.info("Trashing empty posts in WordPress")
    result = trash_empty_posts(status="publish")
    logger.info("Trashed %d empty published posts out of %d found.", result["trashed"], result["found"])

def cmd_tag_opinions():
    """Run opinion tagger to add tags to opinions based on their content."""
    from opinion_tagger import run_backfill
    logger.info("Running opinion tagger")
    asyncio.run(run_backfill(dry_run=True, limit=10))

async def cmd_seo_titles():
    """Backfill SEO titles for all CourtOpinions whose seo_title is NULL."""
    from seo_title_generator import backfill_seo_titles
    logger.info("Running SEO title backfill")
    await backfill_seo_titles()

async def cmd_all():
    """Run the full pipeline: scrape -> classify -> analyze -> upload -> promote."""
    try:
        await cmd_scrape("all")
        await cmd_classify()
        await cmd_analyze()
        await cmd_seo_titles()
        cmd_upload()
        await cmd_promote_to_branding()
    except Exception:
        # Let the process exit nonzero so systemd's OnFailure= sends the crash SMS.
        logger.exception("Pipeline run failed")
        raise

    notifier.send(f"Pipeline done. {notifier.status_summary()}")


def main():
    parser = argparse.ArgumentParser(
        description="Opinion Blogger Pipeline CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # scrape
    scrape_parser = subparsers.add_parser("scrape", help="Run scrapers")
    scrape_parser.add_argument(
        "target", nargs="?", default="all",
        choices=["all", "scotx", "coa"],
        help="Which scraper to run (default: all)"
    )

    # classify
    subparsers.add_parser("classify", help="Run LLM classification on pending-analysis rows")

    # analyze
    subparsers.add_parser("analyze", help="Run opinion analyzer and blog post generator")

    # upload
    subparsers.add_parser("upload", help="Run WordPress uploader")

    # all
    subparsers.add_parser("all", help="Run full pipeline (scrape + analyze + upload)")

    # repair
    subparsers.add_parser("repair-case-names", help="Run repair functions for case names")
    subparsers.add_parser("repair-q-and-a", help="Run repair functions for Q&A")
    subparsers.add_parser("delete-empty", help="Delete opinions that have no content after scraping")
    subparsers.add_parser("trash-empty-drafts", help="Trash empty drafts in WordPress")
    subparsers.add_parser("trash-empty-posts", help="Trash empty published posts in WordPress")

    # index
    subparsers.add_parser("index", help="Run Google indexing for opinions that haven't been indexed yet")

    # Promote to Branding
    subparsers.add_parser("promote-to-branding", help="Run promote to branding migration")
    subparsers.add_parser("tag-opinions", help="Run opinion tagger to add tags to opinions based on their content")
    subparsers.add_parser("seo-titles", help="Backfill SEO titles for CourtOpinions whose seo_title is NULL")

    args = parser.parse_args()

    ensure_directories()

    # Log some configuration info
    logger.info(f"LLM Vendor: {settings.llm_vendor}")
    logger.info(f"LLM Chat Temperature: {settings.llm_chat_temperature}")
    logger.info(f"LLM Strategy Temperature: {settings.llm_strategy_temperature}")

    # Default to "all" if no command given
    command = args.command or "all"

    if command == "scrape":
        asyncio.run(cmd_scrape(args.target))
    elif command == "classify":
        asyncio.run(cmd_classify())
    elif command == "analyze":
        asyncio.run(cmd_analyze())
    elif command == "upload":
        cmd_upload()
    elif command == "all":
        asyncio.run(cmd_all())
    elif command == "repair-case-names":
        asyncio.run(cmd_repair_case_names())
    elif command == "repair-q-and-a":
        asyncio.run(cmd_repair_q_and_a())
    elif command == "index":
        from post_migrator import index_opinions_with_google
        index_opinions_with_google()
    elif command == "delete-empty":
        from post_migrator import delete_empty_opinions
        asyncio.run(delete_empty_opinions())
    elif command == "promote-to-branding":
        asyncio.run(cmd_promote_to_branding())
    elif command == "trash-empty-drafts":
        cmd_trash_empty_drafts()
    elif command == "trash-empty-posts":
        cmd_trash_empty_posts()
    elif command == "tag-opinions":
        cmd_tag_opinions()
    elif command == "seo-titles":
        asyncio.run(cmd_seo_titles())
    else:
        logger.error("Unknown command: %s", command)

if __name__ == "__main__":
    logger.info("Starting scraper job")
    main()
    logger.info("Scraper job finished")
