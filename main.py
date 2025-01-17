import os
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status

# Selenium / BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, db

# Boto3 for local MinIO
import boto3

app = FastAPI(title="Selenium Scraper with Firebase + MinIO Example")

DAILY_LIMIT = 5


# ---------------------------
# 1) Firebase Initialization
# ---------------------------
@app.on_event("startup")
def startup_event():
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase_service_account.json")
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://etheriatech-ec74a-default-rtdb.firebaseio.com"
        })


def get_users_ref():
    return db.reference("users")


# ---------------------------
# 2) MinIO (S3-like) Setup
#admin/admin123
# ---------------------------
MINIO_ENDPOINT = "http://s3.roamingproxy.com:9000"
MINIO_ACCESS_KEY = "Ob85WJ2ql3EWfkDbI0K4"
MINIO_SECRET_KEY = "WdE3eE912C2psnMnHKIlZGezfYCgZxoHEt04R9M4"
MINIO_BUCKET_NAME = "gserp-temp"
import os
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

# ---------- Firebase Admin ----------
import firebase_admin
from firebase_admin import credentials, db

# ---------- Selenium / BeautifulSoup ----------
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

app = FastAPI(title="Selenium Scraper with Firebase Example")

# Daily usage limit for demonstration (per user)
DAILY_LIMIT = 5

# --------------------------------------------------------------------
# 1) Initialize Firebase on startup
# --------------------------------------------------------------------
@app.on_event("startup")
def startup_event():
    """
    We initialize Firebase Admin once the application starts.
    Make sure you have firebase_service_account.json in the project folder,
    or adjust if using environment variables for the credentials.
    """
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase_service_account.json")
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://YOUR-FIREBASE-PROJECT.firebaseio.com"
        })


def get_users_ref():
    """ Reference to /users in the Realtime Database """
    return db.reference("users")


# --------------------------------------------------------------------
# 2) Create a user (endpoint) - For demonstration
# --------------------------------------------------------------------
@app.post("/create_user")
def create_user(api_key: str):
    """
    Creates a new user node in the Realtime Database.
    Example usage:
      POST /create_user?api_key=XYZ123
    """
    users_ref = get_users_ref()
    user_ref = users_ref.child(api_key).get()

    if user_ref:
        raise HTTPException(
            status_code=400, detail="User with this API key already exists."
        )

    # Initialize the user record with usage_count=0 and last_reset=today
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    new_user_data = {
        "usage_count": 0,
        "last_reset": today_str
    }
    users_ref.child(api_key).set(new_user_data)

    return {"message": f"User created with API key '{api_key}'.", "data": new_user_data}


# --------------------------------------------------------------------
# 3) Standalone Selenium function: scrape_google
# --------------------------------------------------------------------
def scrape_google(query: str):
    """
    1) Launch Chrome headless
    2) Search Google for 'query'
    3) Parse result links
    4) Return links
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from bs4 import BeautifulSoup
    import time

    google_search_url = f"https://www.google.com/search?q={query}"

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.82 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(google_search_url)
    time.sleep(2)  # Wait for the page to load

    page_source = driver.page_source
    driver.quit()

    soup = BeautifulSoup(page_source, "html.parser")

    links = []
    for g in soup.find_all("div", class_="g"):
        a_tag = g.find("a")
        if a_tag and "href" in a_tag.attrs:
            links.append(a_tag["href"])

    return links


# --------------------------------------------------------------------
# 4) Search route: usage check + scraping
# --------------------------------------------------------------------
@app.get("/search")
def search(request: Request, query: str):
    """
    1) Check the user's API key (from x-api-key header).
    2) Check usage limit (example daily limit).
    3) If under limit, do the Selenium search, increment usage, return results.
    """
    # 4a) Validate the user's API key from header
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-api-key in header."
        )

    # 4b) Check the user's record in Firebase
    users_ref = get_users_ref()
    user_data = users_ref.child(api_key).get()

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key."
        )

    usage_count = user_data.get("usage_count", 0)
    last_reset = user_data.get("last_reset")

    # 4c) Daily usage reset
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if not last_reset or last_reset != today_str:
        usage_count = 0
        users_ref.child(api_key).update({"usage_count": usage_count, "last_reset": today_str})

    # 4d) Check limit
    if usage_count >= DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily usage limit reached. Please wait until tomorrow or upgrade your account."
        )

    # 4e) If allowed, increment usage
    usage_count += 1
    users_ref.child(api_key).update({"usage_count": usage_count})

    # 4f) Perform the scraping via the function we defined above
    results = scrape_google(query)

    # 4g) Return usage info + results
    return {
        "api_key": api_key,
        "usage_count": usage_count,
        "results": results
    }
