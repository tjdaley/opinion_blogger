"""
txcourts_scotx_scraper - A script to scrape Texas Supreme Court opinions from txcourts.gov.
"""
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from util.settings import settings

from core import download_pdf, get_pdf_text, analyze_with_full_text, review_non_family_cases, sheet, http

# --- CONFIGURATION (Reusing your .env variables) ---
OPINION_LOCAL_PATH = settings.opinion_local_path
POSTS_LOCAL_PATH = settings.posts_local_path
GOOGLE_SHEET_NAME = settings.google_sheet_name
JSON_KEYFILE = settings.json_keyfile
OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model
MAX_OPINION_SIZE = settings.max_opinion_size

TX_COURTS_BASE = "https://www.txcourts.gov"
TX_START_URL = f"{TX_COURTS_BASE}/supreme/orders-opinions/"

# --- PREPARE DIRECTORIES ---
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)


def scrape_tx_courts():
    print(f"Checking main page: {TX_START_URL}")
    resp = http.get(TX_START_URL)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Step 1: Find the "Recently Released" list
    heading = soup.find('h2', string="Recently Released")  # type: ignore
    if not heading:
        print("Could not find 'Recently Released' heading.")
        return
    
    links: list[dict[str, str]] = heading.find_next('ul').find_all('a')  # type: ignore
    if not links:
        print("No links found under 'Recently Released'.")
        return

    existing_dockets = sheet.col_values(1)

    for date_link in links:  # type: ignore
        page_url = TX_COURTS_BASE + date_link.get('href', '')  # type: ignore

        # Convert date string from December 25, 2025 to YYYY-MM-DD unless already in that format
        opinion_date_str = date_link.get_text(strip=True)  # type: ignore
        if re.match(r'^\d{4}-\d{2}-\d{2}$', opinion_date_str):  # type: ignore
            opinion_date = datetime.strptime(opinion_date_str, "%Y-%m-%d")  # type: ignore
        else:
            opinion_date = datetime.strptime(opinion_date_str, "%B %d, %Y")  # type: ignore
        opinion_date_str = opinion_date.strftime("%Y-%m-%d")

        print(f"--- Processing Date: {opinion_date_str} ---")
        
        page_resp = http.get(page_url)  # type: ignore
        page_soup = BeautifulSoup(page_resp.text, 'html.parser')
        
        # Step 2: Find all PDF links matching the "pc" or "digit" pattern
        # Regex: Ends with digits+.pdf or digits+pc.pdf
        pdf_pattern = re.compile(r'\d{6}+(pc)?\.pdf$', re.IGNORECASE)
        pdf_anchors = page_soup.find_all('a', href=pdf_pattern)
        pdf_anchors = [a for a in pdf_anchors if 'case-summaries' not in a['href']]
        
        for anchor in pdf_anchors:
            pdf_url = TX_COURTS_BASE + anchor['href']  # type: ignore
            
            # Step 3: Backtrack to find Case Number and Name
            # The structure is messy, so we look for the nearest preceding <tr> 
            # that contains a div with class 'a50' (Case Number)
            parent_tr = anchor.find_parent('tr')
            case_num = None
            case_name = ""
            
            # Traverse upwards/previous to find the <tr> that holds the case metadata
            current_search = parent_tr
            while current_search and not case_num:
                a50_div = current_search.find('div', class_='a50')
                if a50_div:
                    case_num = a50_div.get_text(strip=True)
                    a54_div = current_search.find('div', class_='a54')
                    case_name = a54_div.get_text(strip=True) if a54_div else "Unknown Case Name"
                current_search = current_search.find_previous_sibling('tr')

            if not case_num or case_num in existing_dockets:
                if case_num in existing_dockets:
                    print(f"Skipping existing or duplicate case: {case_num}")
                else:
                    print("Could not find Case Number for PDF:", pdf_url)  # type: ignore
                continue

            print(f"Found New Case: {case_num} - {case_name}")
            
            # Step 4: Process the case
            pdf_path = download_pdf(pdf_url, case_num)  # type: ignore
            if not pdf_path: continue
            
            full_text = get_pdf_text(pdf_path)
            analysis = analyze_with_full_text(case_name, full_text)
            
            # Save to Sheet (Using your same row format)
            status = "pending-blog" if analysis['family_law'] else "pending-review"
            row_data = [  # type: ignore
                case_num, status, str(analysis['family_law']), 
                analysis['headline'], analysis['legal_issue'], 
                analysis['holding'], pdf_url, 
                datetime.now().strftime("%Y-%m-%d"), "SCOTX", opinion_date_str,
                analysis['case_name'], analysis['lower_court_name'], analysis['seo_title'],
                analysis['seo_focuskw'], analysis['meta_description']
            ]
            sheet.append_row(row_data)  # type: ignore
            existing_dockets.append(case_num) # Update local list to prevent dupes in same run
            print(f"Success: {case_num} added to sheet.")

    review_non_family_cases()

if __name__ == "__main__":
    scrape_tx_courts()
