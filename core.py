import os
from typing import List
import requests
import fitz  # pyright: ignore[reportMissingTypeStubs] # PyMuPDF
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from util.settings import settings

from db.models.opinion_tracking import OpinionTrackingInDB
from db.repositories.opinion_tracking import OpinionTrackingRepository
from db.supabasemanager import SupabaseManager
from agents.family_angle_agent import family_angle_agent, user_prompt as family_angle_user_prompt, FamilyAngle
from agents.case_analysis_agent import case_analysis_agent, user_prompt as case_analysis_user_prompt, CaseAnalysis
from util.loggerfactory import LoggerFactory

logger = LoggerFactory.create_logger(__name__)

# --- CONFIGURATION ---
OPINION_LOCAL_PATH = settings.opinion_local_path
POSTS_LOCAL_PATH = settings.posts_local_path
SCOTX_URL = settings.scotx_url
MAX_OPINION_SIZE = settings.max_opinion_size

# --- DB CONNECTION ---
manager = SupabaseManager()
opinion_repo = OpinionTrackingRepository(manager)

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
        logger.error("Error reading PDF %s: %s", filepath, e)
    return text[:MAX_OPINION_SIZE]  # type: ignore

async def analyze_with_full_text(case_name: str, full_text: str) -> CaseAnalysis:
    """
    Uses the actual opinion text to extract professional legal data.
    
    Arguments:
        case_name -- Name of the case
        full_text -- Full text of the court opinion

    Returns:
        Instance of CaseAnalysis
    """
    prompt = case_analysis_user_prompt.format(case_name=case_name, opinion_text=full_text)
    result = await case_analysis_agent.run(user_prompt=prompt)
    return result.output

def opinion_text(row: OpinionTrackingInDB) -> str:
    """
    Retrieves the opinion text for a given case row.
    Arguments:
        row -- An instance of OpinionTrackingInDB representing a case
    Returns:
        Extracted opinion text
    """
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row.case_number}.pdf")
    _text = get_pdf_text(pdf_path) if os.path.exists(pdf_path) else ""
    return _text

async def review_non_family_cases():
    """
    Reviews 'pending-review' cases (including Criminal) for Family Law relevance.
    """
    records, _ = opinion_repo.select_many(
        condition={"status": "pending-review", 'is_family_law': False}
    )
    records: List[OpinionTrackingInDB]
    
    for row in records:
        case_name = row.headline
        opinion_txt = opinion_text(row)
        
        # We use the updated strategist prompt here
        prompt = family_angle_user_prompt.format(
            case_name=case_name, 
            opinion_text=opinion_txt
        )
        result = await family_angle_agent.run(user_prompt=prompt)

        review: FamilyAngle = result.output
        
        if review.is_procedurally_relevant:
            row.status = "pending-blog"
            # We store the specific "angle" in the headline or a dedicated metadata field
            row.headline = f"CROSSOVER: {review.new_headline}"
            logger.info("Upgraded %s (Court: %s) to pending-blog.", row.case_number, row.court)
        else:
            row.status = "rejected"
            logger.info("Permanently rejected %s.", row.case_number)
            
        opinion_repo.update(row.id, row.model_dump(mode="json"))

async def xreview_non_family_cases():
    """
    Reviews cases marked as 'pending-review' to see if they have procedural relevance.

    Arguments:
        None
    Returns:
        None
    """
    # Get all records that were not clearly family law cases and that are pending review
    records, _ = opinion_repo.select_many(condition={"status": "pending-review", 'is_family_law': False})  # type: ignore
    records: List[OpinionTrackingInDB]
    for row in records:
        case_name = row.headline
        
        opinion_txt = opinion_text(row)
        prompt = family_angle_user_prompt.format(case_name=case_name, opinion_text=opinion_txt)
        result = await family_angle_agent.run(user_prompt=prompt)

        review: FamilyAngle = result.output
        # Update the Sheet
        if review.is_procedurally_relevant:
            row.status = "pending-blog"
            row.headline = review.new_headline
            logger.info("Upgraded %s to pending-blog.", row.case_number)
        else:
            row.status = "rejected"
            logger.info("Permanently rejected %s.", row.case_number)
        opinion_repo.update(row.id, row.model_dump(mode="json"))

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

    # Browser headers to avoid 403 blocks
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'DNT': '1',
        'Sec-CH-UA': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'Sec-CH-UA-Mobile': '?0',
        'Sec-CH-UA-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin'
    }

    response = http.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        with open(full_path, 'wb') as f:
            f.write(response.content)
        return full_path
    logger.error("Failed to download PDF from %s for case %s. Status code: %d", url, case_number, response.status_code)
    return None
