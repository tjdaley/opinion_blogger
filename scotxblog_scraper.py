"""
scotxblog_scraper.py - A script to scrape Texas appellate court opinions.

This scraper is designed to scrape https://data.scotxblog.com/scotx/staging/decided
"""
import asyncio
from datetime import datetime
from uuid import uuid4
from bs4 import BeautifulSoup
from util.settings import settings

from core import download_pdf, get_pdf_text, http
from db.models.opinion_tracking import OpinionTracking
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

# --- CONFIGURATION ---
SCOTX_URL = settings.scotx_url
TABLE_ELEMENT_ID = settings.table_element_id

async def run_scotx_bot():
    """
    Main function to run the SCOTX case scraper and analyzer.

    Arguments:
        None
    Returns:
        None
    """
    try:
        logger.info("Downloading case list from %s", SCOTX_URL)
        resp = http.get(SCOTX_URL, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        logger.error("Could not reach SCOTX blog: %s", e)
        return

    table = soup.find('table', id=TABLE_ELEMENT_ID)
    if not table:
        logger.error("Error - Could not find table having ID %s", TABLE_ELEMENT_ID)
    rows = soup.find('table', id=TABLE_ELEMENT_ID).find_all('tr')  # type: ignore

    # Initial pass to see if directly related to a family law topic.
    logger.info("Processing cases - initial pass for family cases")
    for row in rows:
        tds = row.find_all('td')
        if not tds: continue

        case_num = tds[0].get_text(strip=True)
        if opinion_tracking_repo.exists("case_number", case_num):
            logger.info("Case %s already exists in the repository. Skipping.", case_num)
            continue

        case_name = tds[1].find(string=True, recursive=False).strip()  # type: ignore
        link_tag = tds[1].find('a', class_='btn-mini')

        if not link_tag or "Dissenting" in link_tag.get_text(): continue

        # 1. Download
        pdf_path = download_pdf(link_tag['href'], case_num)  # type: ignore
        if not pdf_path: continue

        # 2. Extract Text (LLM classification is handled by classify_opinions stage)
        opinion_text = get_pdf_text(pdf_path)

        # 3. Save raw scraped row at status='pending-analysis'
        opinion = OpinionTracking(
            case_number=case_num,
            status="pending-analysis",
            is_family_law=False,
            headline=f"{case_name} (SCOTX)",
            legal_issue="",
            holding="",
            opinion_link=link_tag['href'],  # type: ignore
            processed_at=datetime.now(),
            court="SCOTX",
            opinion_date=datetime.strptime(tds[2].get_text(strip=True), "%Y-%m-%d").date(),
            case_name=case_name,
            case_key=str(uuid4()),
            opinion_text=opinion_text
        )
        try:
            opinion_tracking_repo.insert(opinion.model_dump(mode="json"))
            logger.info("Scraped %s: %s", case_num, case_name)
        except Exception as e:
            logger.error(e)

if __name__ == "__main__":
    logger.info("Starting SCOTXBLOG scraper bot")
    asyncio.run(run_scotx_bot())
