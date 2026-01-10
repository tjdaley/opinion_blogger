from datetime import datetime
import os
from typing import Union
import gspread
import json
import fitz  # pyright: ignore[reportMissingTypeStubs] # PyMuPDF
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
MAX_OPINION_SIZE = settings.max_opinion_size

# Connect to LLM
client = OpenAI(api_key=OPENAI_API_KEY)

# Prepare output paths
for path in [OPINION_LOCAL_PATH, POSTS_LOCAL_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

# --- GOOGLE SHEETS SETUP ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)  # type: ignore
gc = gspread.authorize(creds)  # type: ignore
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

def get_pdf_text(filepath: str) -> str:
    """Extracts the first MAX_OPINION_SIZE characters from the PDF for AI analysis."""
    text = ""
    try:
        with fitz.open(filepath) as doc:
            # We usually only need the first few pages for the summary/holding
            for page in doc[:5]: 
                text += page.get_text()  # type: ignore
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return text[:MAX_OPINION_SIZE]  # type: ignore

def opinion_text(row: dict[str, Union[str, int, float]]) -> Union[str, None]:
    # We fetch the PDF text we already downloaded
    pdf_path = os.path.join(OPINION_LOCAL_PATH, f"{row['Case Number']}.pdf")
    _text = get_pdf_text(pdf_path) if os.path.exists(pdf_path) else ""
    return _text

def generate_blog_post(case_data: dict[str, Union[str, int, float]], opinion_text: str):
    """
    Generates a professional blog post designed for attorney citation.
    """
    print("Opinion text length:", len(opinion_text))
    
    date_object = datetime.strptime(str(case_data['Opinion Date']), "%Y-%m-%d")
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
            _text = opinion_text(row)
            if not _text:
                print(f"Skipping case {row['Case Number']} due to missing opinion text.")
                continue
            post_body = generate_blog_post(row, _text)
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
    
def run_blogger_bot():
    # Generate the blog posts
    print("Generating draft blog posts")
    saved_as, count = generate_blog_posts()
    print(f"Draft {count} blog posts saved to {saved_as}")

if __name__ == "__main__":
    run_blogger_bot()