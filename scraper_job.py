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
    python scraper_job.py instagram [--dry-run]  # Publish tagged posts to Instagram
    python scraper_job.py social {threads|facebook} [--dry-run]  # Publish tagged posts
    python scraper_job.py social-preview {threads|facebook|both} <wp id|url>  # Write posts locally
    python scraper_job.py instagram-preview [content.json | case_key]  # Render IG carousel locally
"""

import argparse
from typing import Any
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

async def cmd_instagram_preview(source: str):
    """Render a carousel locally, without posting.

    `source` is either a content JSON file, or a court_opinion case_key - in
    which case the Instagram agent writes the content from the approved post.
    """
    import json
    from pathlib import Path
    from instagram.models import CarouselContent
    from instagram.renderer import render_slides
    src = Path(source)
    if src.suffix == ".json":
        content = CarouselContent.model_validate(json.loads(src.read_text(encoding="utf-8")))
        # A saved preview's content.json re-renders into its own folder.
        name = src.parent.name if src.stem == "content" else src.stem
    else:
        from db.connection import court_opinion_repo
        from instagram.content import build_carousel
        opinion = court_opinion_repo.select_one(condition={"case_key": source})
        if not opinion:
            logger.error("No court_opinion with case_key %s", source)
            return
        content = await build_carousel(opinion)
        name = opinion.slug or source
    out_dir = Path("instagram_previews") / name
    paths = await render_slides(content, out_dir)
    (out_dir / "content.json").write_text(content.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "caption.txt").write_text(content.caption, encoding="utf-8")
    logger.info("Preview ready: %s (%d slides)", out_dir.resolve() / "carousel.html", len(paths))

async def cmd_instagram(dry_run: bool = False):
    """Publish WordPress posts tagged for Instagram as carousels."""
    from instagram.publisher import publish_pending
    logger.info("Running Instagram publisher%s", " (dry run)" if dry_run else "")
    report = await publish_pending(dry_run=dry_run)
    logger.info(report.summary())
    if report.eventful and not dry_run:
        notifier.reply(report.summary())
    return report

def _fetch_wp_post(ref: str) -> dict[str, Any]:
    """A WordPress post by numeric id or by its public URL."""
    import requests
    auth = (settings.wp_username, settings.wp_app_password)
    if ref.isdigit():
        r = requests.get(f"{settings.wp_base_url}/posts/{ref}", params={"context": "edit"}, auth=auth, timeout=30)
        r.raise_for_status()
        return r.json()
    slug = ref.rstrip("/").rsplit("/", 1)[-1]
    found = requests.get(f"{settings.wp_base_url}/posts", params={"slug": slug, "context": "edit"},
                         auth=auth, timeout=30).json()
    if not found:
        raise SystemExit(f"No WordPress post with slug {slug!r}")
    return found[0]

async def cmd_social_preview(channels: list[str], ref: str):
    """Write Threads/Facebook posts for one WordPress post, locally, without posting."""
    from pathlib import Path
    from social.compose import compose
    from social.source import from_wp
    from post_migrator import get_tag_id
    src = from_wp(_fetch_wp_post(ref))
    attorneys_tag = get_tag_id(settings.social_audience_attorneys_tag)
    public_tag = get_tag_id(settings.social_audience_public_tag)
    out_dir = Path("social_previews")
    out_dir.mkdir(exist_ok=True)
    for ch in channels:
        c = await compose(ch, src, attorneys_tag, public_tag)
        path = out_dir / f"{src.wp_id}-{ch}.txt"
        path.write_text(f"[{ch} | audience: {c.audience} | {c.audience_reason}]\n"
                        f"[link card: {c.link}]\n[{len(c.text)} chars]\n\n{c.text}\n", encoding="utf-8")
        logger.info("Preview: %s", path.resolve())

async def cmd_social(channel: str, dry_run: bool = False):
    """Publish WordPress posts tagged for Threads or Facebook."""
    from social.publisher import publish_pending
    report = await publish_pending(channel, dry_run=dry_run)
    logger.info(report.summary())
    if report.eventful and not dry_run:
        notifier.reply(report.summary())
    return report

async def publish_scheduled_channels() -> list[str]:
    """Run each scheduled network's publisher and return summaries worth reporting.

    Isolated per network: one failing (bad token, platform outage) is reported
    and the others still run. Never raises, so it can't fail the pipeline.
    """
    from instagram.publisher import publish_pending as publish_instagram
    from social.publisher import publish_pending as publish_social
    lines: list[str] = []
    for channel in [c.strip() for c in settings.social_scheduled_channels.split(",") if c.strip()]:
        try:
            if channel == "instagram":
                report = await publish_instagram()
            else:
                report = await publish_social(channel)
            logger.info(report.summary())
            if report.eventful:
                lines.append(report.summary())
        except Exception as e:
            logger.exception("Scheduled %s publish failed", channel)
            lines.append(f"{channel.title()}: error: {e}")
    return lines

async def cmd_all():
    """Run the full pipeline: scrape -> classify -> analyze -> upload -> promote -> social."""
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

    social_lines = await publish_scheduled_channels()
    notifier.reply("\n".join([f"Pipeline done. {notifier.status_summary()}"] + social_lines))


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
    ig = subparsers.add_parser("instagram", help="Publish WordPress posts tagged for Instagram")
    ig.add_argument("--dry-run", action="store_true", help="List what would be posted; post nothing")
    soc = subparsers.add_parser("social", help="Publish WordPress posts tagged for Threads or Facebook")
    soc.add_argument("channel", choices=["threads", "facebook"])
    soc.add_argument("--dry-run", action="store_true", help="List what would be posted; post nothing")
    soc_preview = subparsers.add_parser("social-preview", help="Write Threads/Facebook posts locally for one WP post")
    soc_preview.add_argument("channel", choices=["threads", "facebook", "both"])
    soc_preview.add_argument("post", help="WordPress post id or URL")
    ig_preview = subparsers.add_parser("instagram-preview", help="Render an Instagram carousel locally from a content JSON file")
    ig_preview.add_argument("source", nargs="?", default="instagram/fixtures/mcdowell.json",
                            help="content .json file, or a court_opinion case_key")

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
    elif command == "social":
        asyncio.run(cmd_social(args.channel, dry_run=args.dry_run))
    elif command == "social-preview":
        chans = ["threads", "facebook"] if args.channel == "both" else [args.channel]
        asyncio.run(cmd_social_preview(chans, args.post))
    elif command == "instagram":
        asyncio.run(cmd_instagram(dry_run=args.dry_run))
    elif command == "instagram-preview":
        asyncio.run(cmd_instagram_preview(args.source))
    else:
        logger.error("Unknown command: %s", command)

if __name__ == "__main__":
    logger.info("Starting scraper job")
    main()
    logger.info("Scraper job finished")
