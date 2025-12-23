# opinion_blogger
An automated pipeline for Texas family law litigators to identify, analyze, and publish blog content based on recent appellate opinions from the Texas Supreme Court (SCOTX) and Courts of Appeals.

## Overview

This project automates the high-value, labor-intensive task of "case law watching." It monitors Texas appellate courts, uses AI to filter for family law relevance or procedural "crossover" value, and generates attorney-to-attorney blog drafts optimized for SEO and LLM (Large Language Model) citation.

### The Problem

Appellate courts release batches of opinions (often on Friday mornings). Manually reviewing these for relevant family law developments is time-consuming. Most law firms either miss key cases or post "marketing-heavy" summaries that lack the technical depth required to be cited by other researchers or AI tools.

### The Solution

A Python-driven workflow that:

1. **Scrapes:** Monitors `scotxblog.com` and TJB sources for new decisions.
2. **Filters:** Uses GPT-4o to identify family law cases and "procedural crossover" (e.g., new standards for summary judgment or hearsay).
3. **Analyzes:** Reads the actual PDF text via PyMuPDF to extract the **Holding** and **Legal Issue**.
4. **Publishes:** Sends structured, SEO-optimized drafts directly to a WordPress site via the REST API.

## Tech Stack

* **Language:** Python 3.10+
* **AI:** OpenAI API (GPT-4o) for legal reasoning and ghostwriting.
* **Data:** Google Sheets API (as a lightweight CRM/Database).
* **PDF Parsing:** `PyMuPDF` (fitz) for high-fidelity legal text extraction.
* **Web:** `BeautifulSoup4` for scraping and `Requests` with robust retry logic.
* **CMS:** WordPress REST API for automated drafting.

##  Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/tjdaley/blog_writer.git
cd blogwriter
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file or update the configuration section in the script with the following:

* `OPENAI_API_KEY`: Your OpenAI API key.
* `service_account.json`: Your Google Cloud Service Account credentials (placed in the root directory).
* `WORDPRESS_NAME` & `WORDPRESS_PASSWORD`: Your WordPress Application Passwords.
* `OPINION_LOCAL_PATH`: Local directory for PDF storage (e.g., `Z:/Client Files/...`).
* `POSTS_LOCAL_PATH`: = Local directory where blog post json files will be saved to.
* `GOOGLE_SHEET_NAME`: "Texas Appellate Blog Tracker"
* `JSON_KEYFILE`: "name of your keyfile.json"
* `MAX_OPINION_SIZE`: 12000
* `OPENAI_API_KEY`: Your OpenAI Key
* `OPENAI_MODEL`: "gpt-5-mini"
* `WP_BASE_URL`: https://your-web-site-url/wp-json/wp/v2
* `WP_USERNAME`: Your wordpress username
* `WP_APP_PASSWORD`: Your wordpress application password - not your browser password
* `AUTHOR_ID`: ID of the word press author who will be attributed to the post
* `CATEGORY_IDS`: CXomma-separated list of category ids to apply to each blog post
* `TAG_IDS`: Comma-separated list of tag ids to apply to each blog post
* `MEDIA_ID`: ID of media file that will be used as the feature image for each post
* `TABLE_ELEMENT_ID` = "stagingDateTable"
* `SCOTX_URL`: "https://data.scotxblog.com/scotx/staging/decided"

## Project Structure

* **`case_scraper.py`**: The "Scout." Scrapes the court websites and populates the Google Sheet.
* **`opinion_analyzer.py`**: The "Clerk." Downloads PDFs, extracts text, and performs AI analysis.
* **`wp_uploader.py`**: The "Publisher." Converts Markdown to HTML and pushes drafts to WordPress.
* **`requirements.txt`**: List of necessary Python libraries.
* **`.env`**: Environment variables used by the Python files

## Legal Disclaimer

This tool is for educational and legal research purposes. It is not a substitute for the independent professional judgment of an attorney. Always verify AI-generated summaries against the official court opinion before publication.

**Note on Web Scraping:** This bot is designed to respect court servers by using `urllib3` retry strategies and intentional timeouts to avoid excessive load on government infrastructure.

## Roadmap

* [ ] **Image Generation:** Integrate DALL-E 3 or Midjourney API for automated 1200x600 featured images.
* [ ] **Email Alerts:** Add an automated SMTP module to email the firm's partners whenever a "pending-blog" case is identified.
* [ ] **Supabase Migration:** Move from Google Sheets to a robust PostgreSQL database for long-term case indexing.

**Author:** Thomas J. Daley
**Practice:** Family Law Litigation, Texas
**Contact:** [thomasjdaley.com](https://www.thomasjdaley.com)
