from datetime import datetime, timedelta
from urllib.parse import urljoin
from bs4 import BeautifulSoup, ResultSet
from bs4.element import NavigableString
from uuid import uuid4

from core import download_pdf, get_pdf_text, analyze_with_full_text, http, BROWSER_HEADERS
from db.models.opinion_tracking import OpinionTracking
from db.connection import opinion_tracking_repo
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__, "DEBUG")

# --- CONFIGURATION ---
BASE_URL = settings.coa_base_url
COA_LIST = [f"coa{i:02d}" for i in range(1, 15)]
LOOKBACK_DAYS = settings.coa_lookback_days

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

            # Prepare POST data with all required form fields
            current_year = datetime.now().year
            post_data = {  # type: ignore
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': viewstate.get('value', ''),
                '__VIEWSTATEGENERATOR': viewstategenerator.get('value', '') if viewstategenerator else '',
                '__EVENTVALIDATION': eventvalidation.get('value', '') if eventvalidation else '',
                'ctl00$ContentPlaceHolder1$ddlYear': str(current_year),
                'ctl00$ContentPlaceHolder1$ddlQuarter': '01-01-',  # Q1
                'ctl00$ContentPlaceHolder1$btnSearch': 'Refresh',
                'ctl00_ContentPlaceHolder1_grdDocketDates_ClientState': ''
            }

            # Make POST request to get the actual data (include headers to avoid 403)
            resp = http.post(index_url, data=post_data, headers=headers, timeout=20)  # type: ignore
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Debug: Print all table IDs to see what's actually on the page
            all_tables = soup.find_all('table', id=True)
            logger.debug("Found %d tables with IDs: %s", len(all_tables), [t.get('id') for t in all_tables])

            date_table = soup.find('table', id=lambda x: x and x.endswith('grdDocketDates_ctl00'))  # type: ignore
            if not date_table:
                logger.warning("Date table not found. Skipping %s", coa)
                continue

            links = date_table.find_all('a', href=lambda x: x and "FullDate=" in x)  # type: ignore
            links: ResultSet[NavigableString]

            if not links:
                logger.warning("No navigable date links found. Skipping %s", coa)
                continue

            for link in links:  # type: ignore
                date_text = link.get_text(strip=True)  # type: ignore
                if not date_text:
                    continue
                logger.info("--- Processing Date: %s ---", date_text)  # type: ignore
                if date_text and is_recent(date_text):  # type: ignore
                    docket_url = urljoin(BASE_URL, link['href'])  # type: ignore
                    logger.info("Found recent date %s. Processing docket page: %s", date_text, docket_url)  # type: ignore
                    await process_docket_page(coa, docket_url, date_text)  # type: ignore
                else:
                    logger.info("Skipping date %s as it is outside the lookback window.", date_text)  # type: ignore

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

                # --- DOWNLOAD & ANALYSIS ---
                pdf_path = download_pdf(pdf_url, case_num)
                if not pdf_path:
                    logger.error("Failed to download PDF for case %s. URL: %s", case_num, pdf_url)
                    continue

                opinion_text = get_pdf_text(pdf_path)
                analysis = await analyze_with_full_text(case_name, opinion_text)
                logger.info("Analysis for case %s: %s", case_num, analysis)

                # --- DB INSERTION ---
                status = "pending-blog" if analysis.family_law else "pending-review"
                opinion = OpinionTracking(
                    case_number=case_num,
                    status=status,
                    is_family_law=analysis.family_law,
                    headline=analysis.headline or f"{case_name} ({coa_id.upper()})",
                    legal_issue=analysis.legal_issue or disposition,
                    holding=analysis.holding,
                    opinion_link=pdf_url,
                    processed_at=datetime.now(),
                    court=coa_id.upper(),
                    opinion_date=datetime.strptime(release_date, "%m/%d/%Y").date(),
                    case_name=analysis.case_name or case_name,
                    lower_court_name=analysis.lower_court_name or lower_court,
                    seo_title=analysis.seo_title,
                    seo_focus_kw=analysis.seo_focuskw,
                    meta_description=analysis.meta_description,
                    case_key=str(uuid4()),
                    opinion_text=opinion_text
                )

                try:
                    opinion_tracking_repo.insert(opinion.model_dump(mode="json"))
                    logger.info("Processed %s Case %s: %s", "Criminal" if "2" in suffix else "Civil", case_num, case_name)
                except Exception as e:
                    logger.error("Error inserting opinion for case %s: %s", case_num, e)

    except Exception as e:
        logger.error("Error processing docket page %s: %s", url, e)
