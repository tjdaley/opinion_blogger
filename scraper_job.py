"""
scraper_job.py - Runs the scraper, analyzer, and wp_uploader
"""

import asyncio
from txcourts_scotx_scraper import scrape_tx_courts
from tx_coa_scraper import scrape_coa_opinions
from opinion_analyzer import run_blogger_bot
from wp_uploader import run_uploader
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

async def main():
    """Main async function to run all scraper and analysis tasks."""
    await scrape_tx_courts()
    await scrape_coa_opinions()
    await run_blogger_bot()
    run_uploader()


if __name__ == "__main__":
    logger.info("Starting scraper job")
    asyncio.run(main())
    logger.info("Scraper job finished")
