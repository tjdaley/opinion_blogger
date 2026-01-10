"""
scotxblog_scraper.py - A script to scrape Texas appellate court opinions.

This scraper is designed to scrape https://data.scotxblog.com/scotx/staging/decided
"""
from datetime import datetime
import os
from bs4 import BeautifulSoup
from util.settings import settings

from core import download_pdf, get_pdf_text, analyze_with_full_text, review_non_family_cases, sheet, http

# --- CONFIGURATION ---
OPINION_LOCAL_PATH = settings.opinion_local_path
POSTS_LOCAL_PATH = settings.posts_local_path
GOOGLE_SHEET_NAME = settings.google_sheet_name
JSON_KEYFILE = settings.json_keyfile
OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model
TABLE_ELEMENT_ID = settings.table_element_id
SCOTX_URL = settings.scotx_url
MAX_OPINION_SIZE = settings.max_opinion_size

# --- PREPARE DIRECTORIES ---
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

def run_scotx_bot():
    """
    Main function to run the SCOTX case scraper and analyzer.

    Arguments:
        None
    Returns:
        None
    """
    try:
        print(f"Downloading case list from {SCOTX_URL}")
        resp = http.get(SCOTX_URL, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"Could not reach SCOTX blog: {e}")
        return
    
    table = soup.find('table', id=TABLE_ELEMENT_ID)
    if not table:
        print("Error - Could not find table having ID {TABLE_ELEMENT_ID}")
    rows = soup.find('table', id=TABLE_ELEMENT_ID).find_all('tr')  # type: ignore
    
    existing_dockets = sheet.col_values(1)
    
    # Initial pass to see if directly related to a family law topic.
    print("Processing cases - initial pass for family cases")
    for row in rows:
        tds = row.find_all('td')
        if not tds: continue
        
        case_num = tds[0].get_text(strip=True)
        if case_num in existing_dockets: continue
        
        case_name = tds[1].find(string=True, recursive=False).strip()  # type: ignore
        link_tag = tds[1].find('a', class_='btn-mini')
        
        if not link_tag or "Dissenting" in link_tag.get_text(): continue
        
        # 1. Download
        pdf_path = download_pdf(link_tag['href'], case_num)  # type: ignore
        if not pdf_path: continue
        
        # 2. Extract Text & Analyze
        opinion_text = get_pdf_text(pdf_path)
        analysis = analyze_with_full_text(case_name, opinion_text)
        
        # 3. Save to Sheet
        status = "pending-blog" if analysis['family_law'] else "pending-review"
        row_data = [ # type: ignore
            case_num, status, str(analysis['family_law']), 
            analysis['headline'], analysis['legal_issue'], 
            analysis['holding'], link_tag['href'], 
            datetime.now().strftime("%Y-%m-%d"), "SCOTX", tds[2].get_text(strip=True),
            analysis['case_name'], analysis['lower_court_name'], analysis['seo_title'],
            analysis['seo_focuskw'], analysis['meta_description']
        ]
        sheet.append_row(row_data)  # type: ignore
        print(f"Processed {case_num}: {analysis['headline']}")
        
    # Follow up pass to see if any cases that weren't directly related to family law
    # might have a procedural or evidentiary element that is relevant to family law attorneys.
    print("Looking for relevant angle in non-faily cases")
    review_non_family_cases()

if __name__ == "__main__":
    run_scotx_bot()