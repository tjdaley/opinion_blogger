"""
scraper_job.py - Runs the scraper, analyzer, and wp_uploader
"""

import asyncio
from txcourts_scotx_scraper import scrape_tx_courts
from opinion_analyzer import run_blogger_bot
from wp_uploader import run_uploader
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

if __name__ == "__main__":
    logger.info("Starting scraper job")
    asyncio.run(scrape_tx_courts())
    asyncio.run(run_blogger_bot())
    run_uploader()
    logger.info("Scraper job finished")
