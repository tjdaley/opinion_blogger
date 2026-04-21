from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from uuid import uuid4

from core import download_pdf, get_pdf_text, http, BROWSER_HEADERS
from db.models.opinion_tracking import OpinionTracking
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__, "DEBUG")

# --- CONFIGURATION ---
BASE_URL = settings.coa_base_url
COA_LIST = [f"coa{i:02d}" for i in range(1, 15)]
LOOKBACK_DAYS = settings.coa_lookback_days

async def _process_date_links(soup: BeautifulSoup, coa: str, label: str):
    """Find date links in the docket-dates grid and process ones inside the lookback window."""
    all_tables = soup.find_all('table', id=True)
    logger.debug("(%s) Found %d tables with IDs: %s", label, len(all_tables), [t.get('id') for t in all_tables])

    date_table = soup.find('table', id=lambda x: x and x.endswith('grdDocketDates_ctl00'))  # type: ignore
    if not date_table:
        logger.warning("(%s) Date table not found for %s.", label, coa)
        return

    links = date_table.find_all('a', href=lambda x: x and "FullDate=" in x)  # type: ignore
    if not links:
        logger.warning("(%s) No navigable date links found for %s.", label, coa)
        return

    for link in links:  # type: ignore
        date_text = link.get_text(strip=True)  # type: ignore
        if not date_text:
            continue
        logger.info("--- (%s) Processing Date: %s ---", label, date_text)  # type: ignore
        if is_recent(date_text):  # type: ignore
            docket_url = urljoin(BASE_URL, link['href'])  # type: ignore
            logger.info("Found recent date %s. Processing docket page: %s", date_text, docket_url)  # type: ignore
            await process_docket_page(coa, docket_url, date_text)  # type: ignore
        else:
            logger.info("Skipping date %s as it is outside the lookback window.", date_text)  # type: ignore


def is_recent(date_str: str) -> bool:
    """Checks if the date string (MM/DD/YYYY) is within the 10-day lookback window."""
    try:
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        return datetime.now() - date_obj <= timedelta(days=LOOKBACK_DAYS)
    except ValueError:
        return False

async def scrape_coa_opinions():
    """Iterates through all 14 COAs and processes recent releases."""
    logger.info("Starting COA scraper bot")
    for coa in COA_LIST:
        index_url = f"{BASE_URL}DocketSrch.aspx?coa={coa}"
        logger.info("Checking court: %s at %s", coa.upper(), index_url)

        try:
            # Headers to mimic a real browser and avoid 403 blocks
            headers = {
                **BROWSER_HEADERS,
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Upgrade-Insecure-Requests': '1',
                'Priority': 'u=0, i'
            }

            # First GET to retrieve the page and extract ViewState
            resp = http.get(index_url, headers=headers, timeout=20)
            logger.debug("GET response status: %s, content-type: %s", resp.status_code, resp.headers.get('content-type'))
            logger.debug("Response length: %d bytes", len(resp.text))

            # Debug: Save the raw HTML response for the index page to analyze structure and potential anti-scraping measures
            with open(f"debug_{coa}.html", "w", encoding="utf-8") as f:
                f.write(resp.text)  # Save the raw HTML for debugging

            initial_soup = BeautifulSoup(resp.text, 'html.parser')

            # Debug: Check for all input fields
            all_inputs = initial_soup.find_all('input', type='hidden')
            logger.debug("Found %d hidden inputs: %s", len(all_inputs), [inp.get('name') for inp in all_inputs])

            # Extract required ASP.NET fields - try both with attrs dict and direct search
            viewstate = initial_soup.find('input', {'name': '__VIEWSTATE'}) or initial_soup.find('input', id='__VIEWSTATE')
            eventvalidation = initial_soup.find('input', {'name': '__EVENTVALIDATION'}) or initial_soup.find('input', id='__EVENTVALIDATION')
            viewstategenerator = initial_soup.find('input', {'name': '__VIEWSTATEGENERATOR'}) or initial_soup.find('input', id='__VIEWSTATEGENERATOR')

            if not viewstate:
                logger.error("Could not find __VIEWSTATE for %s. Response may be redirecting or malformed.", coa)
                logger.debug("First 500 chars of response: %s", resp.text[:500])
                continue

            # The initial GET already returns the current-quarter docket dates
            # (the site's ddlQuarter defaults to the current quarter), so parse it directly.
            await _process_date_links(initial_soup, coa, label="current quarter")

            # If the lookback window crosses into the previous quarter, fetch that too via POST.
            now = datetime.now()
            current_q_month = ((now.month - 1) // 3) * 3 + 1
            days_into_quarter = (now - datetime(now.year, current_q_month, 1)).days
            if days_into_quarter < LOOKBACK_DAYS:
                if current_q_month == 1:
                    prev_year, prev_q_month = now.year - 1, 10
                else:
                    prev_year, prev_q_month = now.year, current_q_month - 3
                prev_q_label = f"{prev_year}-Q{(prev_q_month - 1) // 3 + 1}"
                logger.info("Lookback spans previous quarter; fetching %s via POST.", prev_q_label)

                post_data = {  # type: ignore
                    '__EVENTTARGET': '',
                    '__EVENTARGUMENT': '',
                    '__VIEWSTATE': viewstate.get('value', ''),
                    '__VIEWSTATEGENERATOR': viewstategenerator.get('value', '') if viewstategenerator else '',
                    '__EVENTVALIDATION': eventvalidation.get('value', '') if eventvalidation else '',
                    'ctl00$ContentPlaceHolder1$ddlYear': str(prev_year),
                    'ctl00$ContentPlaceHolder1$ddlQuarter': f'{prev_q_month:02d}-01-',
                    'ctl00$ContentPlaceHolder1$btnSearch': 'Refresh',
                    'ctl00_ContentPlaceHolder1_grdDocketDates_ClientState': ''
                }
                resp = http.post(index_url, data=post_data, headers=headers, timeout=20)  # type: ignore
                with open(f"debug_{coa}_post.html", "w", encoding="utf-8") as f:
                    f.write(resp.text)
                prev_soup = BeautifulSoup(resp.text, 'html.parser')
                await _process_date_links(prev_soup, coa, label=prev_q_label)

        except Exception as e:
            logger.error("Error reaching index for %s: %s", coa, e)

async def process_docket_page(coa_id: str, url: str, release_date: str):
    """Scrapes both Civil and Criminal tables for a specific date."""
    logger.info("Processing Docket: %s for %s (%s)", release_date, coa_id.upper(), url)
    try:
        # Use shared headers with page-specific overrides
        headers = {
            **BROWSER_HEADERS,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Site': 'same-origin',
            'Referer': f'{BASE_URL}DocketSrch.aspx?coa={coa_id}'
        }

        resp = http.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Target both 'Civil Causes Decided' and 'Criminal Causes Decided' tables
        # Based on HTML, these use RadGrid formatting with specific suffixes
        table_ids = ['grdDocket_ctl00', 'grdDocket2_ctl00']

        for suffix in table_ids:
            table = soup.find('table', id=lambda x: x and x.endswith(suffix))  # type: ignore
            if not table:
                logger.warning("Table with suffix %s not found on page. Skipping.", suffix)
                continue

            rows = table.find_all('tr', class_=['rgRow', 'rgAltRow'])
            for row in rows:
                tds = row.find_all('td')
                if len(tds) < 4: continue

                # --- METADATA EXTRACTION ---
                # Cell 0: Case Number and PDF Link
                case_link_tag = tds[0].find('a', href=lambda x: x and "Case.aspx" in x)  # type: ignore
                if not case_link_tag: continue
                case_num = case_link_tag.get_text(strip=True)

                if opinion_tracking_repo.exists("case_number", case_num):
                    logger.info("Case %s already exists. Skipping.", case_num)
                    continue

                # Locate PDF Link inside the nested docGrid table in Cell 0
                pdf_tag = tds[0].find('a', href=lambda x: x and "SearchMedia.aspx" in x)  # type: ignore
                if not pdf_tag: continue
                pdf_url = urljoin(BASE_URL, pdf_tag['href'])  # type: ignore

                # Cell 1: Style and Lower Court
                style_cell = tds[1]
                # Extract bolded text (Party names)
                case_name = style_cell.find('span').get_text(strip=True) if style_cell.find('span') else style_cell.get_text(strip=True)   # type: ignore

                # Lower court name is typically after the <br/>
                full_style_text = style_cell.get_text("|", strip=True)
                lower_court = full_style_text.split("|")[-1] if "|" in full_style_text else "Unknown"

                # Cell 2: Disposition (The ruling)
                disposition = tds[2].get_text(strip=True)

                # --- DOWNLOAD ---
                pdf_path = download_pdf(pdf_url, case_num)
                if not pdf_path:
                    logger.error("Failed to download PDF for case %s. URL: %s", case_num, pdf_url)
                    continue

                opinion_text = get_pdf_text(pdf_path)

                # --- DB INSERTION (status='pending-analysis' is picked up by classify_opinions) ---
                opinion = OpinionTracking(
                    case_number=case_num,
                    status="pending-analysis",
                    is_family_law=False,
                    headline=f"{case_name} ({coa_id.upper()})",
                    legal_issue=disposition,
                    holding="",
                    opinion_link=pdf_url,
                    processed_at=datetime.now(),
                    court=coa_id.upper(),
                    opinion_date=datetime.strptime(release_date, "%m/%d/%Y").date(),
                    case_name=case_name,
                    lower_court_name=lower_court,
                    case_key=str(uuid4()),
                    opinion_text=opinion_text
                )

                try:
                    opinion_tracking_repo.insert(opinion.model_dump(mode="json"))
                    logger.info("Scraped %s Case %s: %s", "Criminal" if "2" in suffix else "Civil", case_num, case_name)
                except Exception as e:
                    logger.error("Error inserting opinion for case %s: %s", case_num, e)

    except Exception as e:
        logger.error("Error processing docket page %s: %s", url, e)
