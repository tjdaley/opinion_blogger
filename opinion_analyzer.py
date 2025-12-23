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
MAX_OPINION_SIZE = os.getenv('MAX_OPINION_SIZE')

# Connect to LLM
client = OpenAI(api_key=OPENAI_API_KEY)

# Prepare output paths
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

def get_pdf_text(filepath):
    """Extracts the first MAX_OPINION_SIZE characters from the PDF for AI analysis."""
    text = ""
    try:
        with fitz.open(filepath) as doc:
            # We usually only need the first few pages for the summary/holding
            for page in doc[:5]: 
                text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return text[:MAX_OPINION_SIZE]

def analyze_with_full_text(case_name, full_text):
    """Uses the actual opinion text to extract professional legal data."""
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
    
    Return ONLY JSON:
    {{
        "family_law": bool,
        "headline": "string",
        "legal_issue": "string",
        "holding": "string"
        "case_name": "string",
        "lower_court_name": "string"
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
    # We fetch the PDF text we already downloaded
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row['Case Number']}.pdf")
    _text = get_pdf_text(pdf_path) if os.path.exists(pdf_path) else ""
    return _text

def generate_blog_post(case_data, opinion_text):
    """
    Generates a professional blog post designed for attorney citation.
    """
    print("Opinion text length:", len(opinion_text))
    
    date_object = datetime.strptime(case_data['Opinion Date'], "%Y-%m-%d")
    opinion_date = date_object.strftime("%B %d, %Y")
    
    if not case_data['Family Law?']:
        additional_instruction = """
    9. CROSSOVER
       (a) Fixed Header Text: "Family Law Crossover"
       (b) Content: Explain how this civil ruling can be weaponized in a Texas divorce or custody case?
       (c) Content Style: Paragraph
       (d) Header Style: H2
"""
    else:
        additional_instruction = ""
    
    prompt = f"""
    You are a high-end Texas Appellate Consultant. Write a blog post for a law firm website 
    targeting Texas Family Law litigators. 
    
    CASE DATA:
    - Case Number: {case_data['Case Number']}
    - Headline: {case_data['Headline']}
    - Initial Issue: {case_data['Legal Issue']}
    - The Holding: {case_data['The Holding']}
    
    OPINION TEXT SNIPPET:
    <opinion>
    {opinion_text[:50000]}
    </opinion>

    STRUCTURE REQUIREMENTS:

    1. BASIC CASE INFORMATION
       (a) Fixed Header Text: None
       (b) Content (line 1): "*{case_data['Case Name']}*, {case_data['Case Number']}, {opinion_date}."
       (b) Content (line 2): "On appeal from {case_data['Lower Court Name']}"
       (c) Content Style: H4
    2. BOTTOM LINE ON TOP
       (a) Fixed Header Text: "Synopsis"
       (b) Content: Generate a 2-3 sentence 'Direct Answer' summary. No fluff.
       (c) Content Style: Paragraph
       (d) Header Style: H2
    3. THE IMPACT ON FAMILY LAW
       (a) Fixed Header Text: "Relevance to Family Law"
       (b) Content: Explicitly explain how this affects divorce, custody, or property litigation (even if the case is commercial/civil).
       (c) Content Style: Paragraph
       (d) Header Style: H2
    4. CASE SUMMARY
       (a) Fixed Header Text: "Case Summary"
       (b) Content: Create multiple subsections, described below.
       (c) Content Style: Paragraph
       (d) Header Style: H2
       (e) SUBSECTIONS:
       4.1 FACT STATEMENT
           (a) Fixed Headline Text: "Fact Summary"
           (b) Content: Discuss the facts relevant to the court's reasoning. We don't want an exhaustive reiteration of the facts, but we need to know enough to understand the opinion. When in doubt, say more rather than less.
           (c) Content Style: Paragraph
           (d) Header Style: H3
       4.2 ISSUES
           (a) Fixed Header Text: "Issues Decided"
           (b) Content: List the issues that the court decided
           (c) Content Style: Paragraph
           (d) Header Style: H3
       4.3 RULES
           (a) Fixed Header Text: "Rules Applied"
           (b) Content: Discuss the statutes and legal precedents that the court applied
           (c) Content Style: Paragraph
           (d) Header Style: H3
       4.4 APPLICATION
           (a) Fixed Header Text: "Application"
           (b) Content: Discuss how the court applied the law to the facts. Discuss it in a narrative form, not a bulleted list. Tell the legal story.
           (c) Content Style: Paragraph
           (d) Header Style: H3
       4.5 HOLDING
           (a) Fixed Header Text: "Holding"
           (b) Content: State the court's holding on the issues before it with a brief discussion of each holding. Each holding should be its own paragraph and again in a narrative, not a bulleted, format.
           (c) Content Style: Paragraph
           (d) Header Style: H3
    5. PRACTICAL TIPS
       (a) Fixed Header Text: "Practical Application"
       (b) Content: Discuss how this case applies to various family law litigation scenarios.
       (c) Content Style: Paragraph
       (d) Header Style: H2
    6. CHECKLIST
       (a) Fixed Header Text: "Checklists"
       (b) Content: Generate checklists, by subtopic, that practitioners can use to apply the holding of the case and how to avoid the downside of what happened to the non-prevailing party.
       (c) Content Style: Paragraph for the check list name, e.g. "Gather Your Evidence"; and bulleted list for items under that list.
       (d) Header Style: h2
    7. CITATION
       (a) Fixed Header Text: "Citation"
       (b) Content: Provide the full formal citation (e.g., *In re Marshall*, __ S.W.3d __).
       (c) Content Style: Paragraph. The name of the case, e.g. "In re Marshall", must be in *italics*.
       (d) Header Style: H2
    8. FULL OPINION
       (a) Fixed Header Text: "Full Opinion"
       (b) Content: Provide the following link to the full opinion. Use Markdown. URL: {case_data['Opinion Link']}
       (c) Content Style: Paragraph
       (d) Header Style: H2
    {additional_instruction}
    
    TONE: Professional, authoritative, and strategic. Avoid layman's terms; speak to peers, in a professional conversational tone and narrative style.
    
    FORMAT: Use Markdown to format the headers, tables, numbered lists, links, and bulleted lists
    
    EXCLUDE: You are generating a blog post. Do not include any other preamble at the top and do not include an offer to do addtional work at the bottem.
    """
    
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": "You are a Texas Board Certified Family Law Attorney."},
                  {"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def generate_blog_posts():
    # Get all records from the sheet
    records = sheet.get_all_records()
    
    post_count = 0
    
    for i, row in enumerate(records):
        if row['Status'] == 'pending-blog':
            post_body = generate_blog_post(row, opinion_text(row))
            if post_body:
                row['body'] = post_body
                post_count += 1
                
                filename = f"draft_{row['Case Number']}.json"
                full_path = os.path.join(POSTS_LOCAL_PATH, filename)
                with open(full_path, 'w') as f:
                    f.write(json.dumps(row))
                    
                row_idx = i + 2
                sheet.update_cell(row_idx, 2, 'blog-drafted') # Column 2 is Status
        
    return POSTS_LOCAL_PATH, post_count
    
def review_non_family_cases():
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
    filename = f"{case_number}.pdf"
    full_path = os.path.join(OPINION_LOCAL_PATH, filename)
    response = requests.get(url, timeout=15)
    if response.status_code == 200:
        with open(full_path, 'wb') as f:
            f.write(response.content)
        return full_path
    return None

def run_scotx_bot():
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
            analysis['case_name'], analysis['lower_court_name']
        ]
        sheet.append_row(row_data)
        print(f"Processed {case_num}: {analysis['headline']}")
        
    # Follow up pass to see if any cases that weren't directly related to family law
    # might have a procedural or evidentiary element that is relevant to family law attorneys.
    print("Looking for relevant angle in non-faily cases")
    review_non_family_cases()
    
    # Now generate the blog posts
    print("Generating draft blog posts")
    saved_as, count = generate_blog_posts()
    print(f"Draft {count} blog posts saved to {saved_as}")

if __name__ == "__main__":
    run_scotx_bot()