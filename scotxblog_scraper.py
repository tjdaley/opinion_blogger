"""
scotxblog_scraper.py - A script to scrape Texas appellate court opinions.

This scraper is designed to scrape https://data.scotxblog.com/scotx/staging/decided
"""
from datetime import datetime
import os
import requests
import gspread
import json
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
OPINION_LOCAL_PATH = os.getenv('OPINION_LOCAL_PATH')
POSTS_LOCAL_PATH = os.getenv('POSTS_LOCAL_PATH')
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')
JSON_KEYFILE = os.getenv('JSON_KEYFILE')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
TABLE_ELEMENT_ID = os.getenv('TABLE_ELEMENT_ID')
SCOTX_URL = os.getenv('SCOTX_URL')
MAX_OPINION_SIZE = int(os.getenv('MAX_OPINION_SIZE'))

# --- OPENAI SETUP ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- PREPARE DIRECTORIES ---
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

# --- GOOGLE SHEETS SETUP ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)
gc = gspread.authorize(creds)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# --- SESSION SETUP ---
def get_robust_session():
    session = requests.Session()
    # Retry strategy: 
    # total=5 (try 5 times), backoff_factor=1 (wait 1s, 2s, 4s, 8s...)
    # status_forcelist (retry on these specific server errors)
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# Initialize global session
http = get_robust_session()

def get_pdf_text(filepath: str) -> str:
    """
    Extracts the first MAX_OPINION_SIZE characters from the PDF for AI analysis.

    Arguments:
        filepath -- path to the PDF file

    Returns:
        Extracted text from the PDF
    """
    text = ""
    try:
        with fitz.open(filepath) as doc:
            # We usually only need the first few pages for the summary/holding
            for page in doc[:5]: 
                text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return text[:MAX_OPINION_SIZE]

def analyze_with_full_text(case_name: str, full_text: str) -> dict:
    """
    Uses the actual opinion text to extract professional legal data.
    
    Arguments:
        case_name -- Name of the case
        full_text -- Full text of the court opinion

    Returns:
        A dictionary with analysis results
    """
    prompt = f"""
    You are an elite Texas Appellate Attorney. 
    Case Name: {case_name}
    
    Examine the provided text from the court opinion:
    {full_text}
    
    1. Is this a Family Law matter? (True/False)
    2. Write a professional headline for a legal blog.
    3. Identify the primary 'Legal Issue' (max 2 sentences).
    4. Summarize 'The Holding' clearly for other attorneys.
    5. Identify the case name, e.g. "In Re T.J.D." or "State v. Alexander"
    6. Extract the name of the lower court from which the appeal was taken, e.g. "Court of Appeals for the Fourth District of Texas", "296th Judicial District Court, Collin County, Texas"
    7. SEO TITLE: Under 60 characters.
    8. SEO FOCUS KEYPHRASE: A 3-5 word phrase attorneys would search for.
    9. META DESCRIPTION: Under 155 characters. Start with the most important legal conclusion.
    
    Return ONLY JSON:
    {{
        "family_law": bool,
        "headline": "string",
        "legal_issue": "string",
        "holding": "string"
        "case_name": "string",
        "lower_court_name": "string",
        "seo_title": "string",
        "seo_focuskw": "string",
        "meta_description": "string"
    }}
    """
    response = client.chat.completions.create(
        model=OPENAI_MODEL, # Using 4o for better legal reasoning
        messages=[{"role": "system", "content": "You provide structured legal analysis."},
                  {"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

def opinion_text(row) -> str:
    """
    Retrieves the opinion text for a given case row.
    Arguments:
        row -- A dictionary representing a row from the Google Sheet
    Returns:
        Extracted opinion text
    """
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row['Case Number']}.pdf")
    _text = get_pdf_text(pdf_path) if os.path.exists(pdf_path) else ""
    return _text

def review_non_family_cases():
    """
    Reviews cases marked as 'pending-review' to see if they have procedural relevance.

    Arguments:
        None
    Returns:
        None
    """
    # Get all records from the sheet
    records = sheet.get_all_records()
    
    for i, row in enumerate(records):
        # Only look at cases we haven't decided to blog on yet
        if row['Status'] == 'pending-review':
            case_name = row['Headline'] # Or use the Case Name column
            
            opinion_txt = opinion_text(row)

            prompt = f"""
            You are a Texas Litigation Strategist. 
            Case: {case_name}
            Content: {opinion_txt[:5000]}
            
            Even though this is NOT a family law case, does it contain a ruling on 
            Texas Civil Procedure or Evidence that would be highly relevant to 
            a Family Law litigator (e.g., discovery, expert witnesses, mandamus, 
            summary judgment, or attorney's fees)?
            
            Return JSON:
            {{
                "is_procedurally_relevant": bool,
                "reasoning": "string (1 sentence)",
                "new_headline": "string (e.g., 'How this Commercial Discovery Ruling impacts Family Law')"
            }}
            """
            
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            review = json.loads(response.choices[0].message.content)
            
            # Update the Sheet
            row_idx = i + 2 # +1 for 0-indexing, +1 for header
            if review['is_procedurally_relevant']:
                sheet.update_cell(row_idx, 2, "pending-blog") # Column 2 is Status
                sheet.update_cell(row_idx, 4, review['new_headline']) # Update headline for the niche
                print(f"Upgraded {row['Case Number']} to pending-blog.")
            else:
                sheet.update_cell(row_idx, 2, "rejected")
                print(f"Permanently rejected {row['Case Number']}.")

def download_pdf(url, case_number):
    """
    Downloads the PDF opinion from the given URL.

    Arguments:
        url -- URL of the PDF
        case_number -- Case number to name the file
    Returns:
        Full path to the downloaded PDF or None if failed
    """
    filename = f"{case_number}.pdf"
    full_path = os.path.join(OPINION_LOCAL_PATH, filename)
    response = requests.get(url, timeout=15)
    if response.status_code == 200:
        with open(full_path, 'wb') as f:
            f.write(response.content)
        return full_path
    return None

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
    rows = soup.find('table', id=TABLE_ELEMENT_ID).find_all('tr')
    
    existing_dockets = sheet.col_values(1)
    
    # Initial pass to see if directly related to a family law topic.
    print("Processing cases - initial pass for family cases")
    for row in rows:
        tds = row.find_all('td')
        if not tds: continue
        
        case_num = tds[0].get_text(strip=True)
        if case_num in existing_dockets: continue
        
        case_name = tds[1].find(string=True, recursive=False).strip()
        link_tag = tds[1].find('a', class_='btn-mini')
        
        if not link_tag or "Dissenting" in link_tag.get_text(): continue
        
        # 1. Download
        pdf_path = download_pdf(link_tag['href'], case_num)
        if not pdf_path: continue
        
        # 2. Extract Text & Analyze
        opinion_text = get_pdf_text(pdf_path)
        analysis = analyze_with_full_text(case_name, opinion_text)
        
        # 3. Save to Sheet
        status = "pending-blog" if analysis['family_law'] else "pending-review"
        row_data = [
            case_num, status, str(analysis['family_law']), 
            analysis['headline'], analysis['legal_issue'], 
            analysis['holding'], link_tag['href'], 
            datetime.now().strftime("%Y-%m-%d"), "SCOTX", tds[2].get_text(strip=True),
            analysis['case_name'], analysis['lower_court_name'], analysis['seo_title'],
            analysis['seo_focuskw'], analysis['meta_description']
        ]
        sheet.append_row(row_data)
        print(f"Processed {case_num}: {analysis['headline']}")
        
    # Follow up pass to see if any cases that weren't directly related to family law
    # might have a procedural or evidentiary element that is relevant to family law attorneys.
    print("Looking for relevant angle in non-faily cases")
    review_non_family_cases()

if __name__ == "__main__":
    run_scotx_bot()