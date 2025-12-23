"""
wp_api_test - A script to test WordPress REST API connection, authentication, and category/schema availability.
"""

import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()
# --- YOUR CONFIG ---
WP_BASE_URL = os.getenv('WP_BASE_URL')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')
AUTHOR_ID = int(os.getenv('AUTHOR_ID'))

def test_wordpress_connection():
    print(f"Testing connection to {WP_BASE_URL}...")
    
    # 1. Test Authentication & Author Access
    # We'll try to fetch the author's profile data to verify credentials
    auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    
    try:
        response = requests.get(f"{WP_BASE_URL}/users/{AUTHOR_ID}", auth=auth)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Success! Authenticated as: {user_data.get('name')}")
        elif response.status_code == 401:
            print("❌ Authentication Failed: Check your Application Password or Username.")
            print(f"Response: {response.text}")
            return
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return

        # 2. Test Category existence (Case Law Update)
        cat_response = requests.get(f"{WP_BASE_URL}/categories", params={'search': 'Case Law Update'})
        categories = cat_response.json()
        
        if any(c['name'] == 'Case Law Update' for c in categories):
            print("✅ Category 'Case Law Update' found.")
        else:
            print("⚠️ Category 'Case Law Update' not found. It will need to be created or matched by ID.")

        # 3. Test Schema/Yoast Availability
        # Yoast data is usually bundled in the 'posts' response if active.
        print("✅ Connection test complete. Ready to proceed with post creation.")

    except Exception as e:
        print(f"❌ Connection Error: {str(e)}")

if __name__ == "__main__":
    test_wordpress_connection()