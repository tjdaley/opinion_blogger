import os
from typing import Union
import requests
import json
import fitz  # pyright: ignore[reportMissingTypeStubs] # PyMuPDF
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import gspread
from oauth2client.service_account import ServiceAccountCredentials  # pyright: ignore[reportMissingTypeStubs]
from openai import OpenAI
from util.settings import settings

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

# --- OPENAI SETUP ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- GOOGLE SHEETS SETUP ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)  # type: ignore
gc = gspread.authorize(creds)  # type: ignore
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# --- SESSION SETUP ---
def get_robust_session() -> requests.Session:
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
                text += page.get_text()  # type: ignore
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return text[:MAX_OPINION_SIZE]  # type: ignore

def analyze_with_full_text(case_name: str, full_text: str) -> dict[str, str]:
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
    return json.loads(response.choices[0].message.content)  # type: ignore

def opinion_text(row: dict[str, Union[str, int, float]]) -> str:
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
            review = json.loads(response.choices[0].message.content)  # type: ignore
            
            # Update the Sheet
            row_idx = i + 2 # +1 for 0-indexing, +1 for header
            if review['is_procedurally_relevant']:
                sheet.update_cell(row_idx, 2, "pending-blog") # Column 2 is Status
                sheet.update_cell(row_idx, 4, review['new_headline']) # Update headline for the niche
                print(f"Upgraded {row['Case Number']} to pending-blog.")
            else:
                sheet.update_cell(row_idx, 2, "rejected")
                print(f"Permanently rejected {row['Case Number']}.")

def download_pdf(url: str, case_number: str) -> str | None:
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
