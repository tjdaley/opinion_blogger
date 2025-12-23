"""
wp_uploader - A script to upload case law updates to WordPress using the REST API.
"""

import os
import json
import requests
from requests.auth import HTTPBasicAuth
import shutil
import markdown
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
POSTS_LOCAL_PATH = os.getenv('POSTS_LOCAL_PATH')
WP_BASE_URL = os.getenv('WP_BASE_URL')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')
POSTS_LOCAL_PATH = os.getenv('POSTS_LOCAL_PATH')
PROCESSED_PATH = os.path.join(POSTS_LOCAL_PATH, "processed")
AUTHOR_ID = int(os.getenv('AUTHOR_ID'))
CATEGORY_IDS = [int(id) for id in os.getenv('CATEGORY_IDS').split(",")]
TAG_IDS = [int(id) for id in os.getenv('TAG_IDS').split(",")]
MEDIA_ID = int(os.getenv('MEDIA_ID'))

if not os.path.exists(PROCESSED_PATH):
    os.makedirs(PROCESSED_PATH)

def upload_to_wordpress(json_data):
    auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    
    html_content = markdown.markdown(
        json_data['body'], 
        extensions=['extra', 'nl2br', 'sane_lists']
    )
    
    # Prepare the payload
    # Note: Yoast SEO fields are often handled via the 'meta' key
    payload = {
        "title": json_data['Headline'],
        "content": html_content,
        "status": "draft",
        "author": AUTHOR_ID,
        "categories": CATEGORY_IDS,
        "tags": TAG_IDS,
        "comment_status": "closed",
        "featured_media": MEDIA_ID,
        "meta": {
            "_yoast_wpseo_title": json_data.get('seo_title', json_data.get('Headline','')),
            "_yoast_wpseo_metadesc": json_data.get('meta_description', json_data.get('Legal Issue',''))[:156], # Meta desc limit
            "_yoast_wpseo_focuskw": json_data.get('seo_focuskw', "Texas Family Law Case Update")
        }
    }

    response = requests.post(f"{WP_BASE_URL}/posts", json=payload, auth=auth)
    
    if response.status_code == 201:
        print(f"✅ Success: Posted {json_data['Case Number']} as Draft.")
        return True
    else:
        print(f"❌ Error posting {json_data['Case Number']}: {response.text}")
        return False

def run_uploader():
    files = [f for f in os.listdir(POSTS_LOCAL_PATH) if f.endswith('.json')]
    
    if not files:
        print("No pending JSON drafts found.")
        return

    for filename in files:
        file_path = os.path.join(POSTS_LOCAL_PATH, filename)
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # We only want to upload cases that were flagged as pending-blog
        if data.get('Status') == 'pending-blog':
            success = upload_to_wordpress(data)
            
            if success:
                # Move to processed folder
                shutil.move(file_path, os.path.join(PROCESSED_PATH, filename))
        else:
            print(f"Skipping {filename} - Status is {data.get('Status')}")

if __name__ == "__main__":
    run_uploader()
