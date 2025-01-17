import os
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, db

# Selenium / BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# Boto3 for MinIO
import boto3

app = FastAPI(title="roamingproxy")

# Daily usage limit for demonstration
DAILY_LIMIT = 5

# --------------------------------------------------------------------
# 1) Firebase Initialization
# --------------------------------------------------------------------
@app.on_event("startup")
def startup_event():
    """
    Initialize Firebase Admin once.
    Make sure 'firebase_service_account.json' is in your project folder,
    or adjust if using environment variables.
    """
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase_service_account.json")
        print(cred.service_account_email)
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://etheriatech-ec74a-default-rtdb.firebaseio.com"
        })


def get_users_ref():
    """ Shortcut to the '/users' node in Realtime DB """
    return db.reference("users")


# --------------------------------------------------------------------
# 2) MinIO (S3-like) Setup
# --------------------------------------------------------------------
# Adjust these for your MinIO environment
MINIO_ENDPOINT = "http://s3.roamingproxy.com:9000"
MINIO_ACCESS_KEY = "Ob85WJ2ql3EWfkDbI0K4"
MINIO_SECRET_KEY = "WdE3eE912C2psnMnHKIlZGezfYCgZxoHEt04R9M4"
MINIO_BUCKET_NAME = "gserp-temp"

# Create a boto3 S3 client pointed at MinIO
s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,       # Key param for MinIO
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name="us-east-1"           # or any region
)

# Ensure the bucket exists (ignore errors if it does)
try:
    s3_client.create_bucket(Bucket=MINIO_BUCKET_NAME)
except s3_client.exceptions.BucketAlreadyOwnedByYou:
    pass
except s3_client.exceptions.BucketAlreadyExists:
    pass


def upload_html_to_minio(html_content: str) -> str:
    """
    1) Generate a unique key (e.g. 'scraped_html/<uuid>.html')
    2) Upload the HTML to MinIO
    3) Return a presigned URL for temporary access
    """
    unique_id = str(uuid.uuid4())
    object_key = f"scraped_html/{unique_id}.html"

    # Upload the HTML
    s3_client.put_object(
        Bucket=MINIO_BUCKET_NAME,
        Key=object_key,
        Body=html_content.encode("utf-8"),
        ContentType="text/html"
    )

    # Generate a presigned URL (valid for 1 hour)
    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": MINIO_BUCKET_NAME, "Key": object_key},
        ExpiresIn=3600  # seconds
    )
    return presigned_url


# --------------------------------------------------------------------
# 3) Create a user in Firebase
# --------------------------------------------------------------------
@app.post("/create_user")
def create_user(api_key: str):
    """
    Example usage: POST /create_user?api_key=TEST123
    """
    users_ref = get_users_ref()
    user_ref = users_ref.child(api_key).get()

    if user_ref:
        raise HTTPException(
            status_code=400, detail="User with this API key already exists."
        )

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    new_user_data = {
        "usage_count": 0,
        "last_reset": today_str
    }
    users_ref.child(api_key).set(new_user_data)

    return {"message": f"User created with API key '{api_key}'.", "data": new_user_data}


# --------------------------------------------------------------------
# 4) Scrape function: uses Selenium to get Google results
# --------------------------------------------------------------------
def scrape_google(query: str):
    """
    1) Launch Chrome headless
    2) Navigate to Google for the query
    3) Return the entire page_source + a parsed list of links
    """
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
    time.sleep(2)  # Let page load

    # Grab page source
    page_source = driver.page_source
    driver.quit()

    # Parse links with BeautifulSoup
    soup = BeautifulSoup(page_source, "html.parser")
    links = []
    for g in soup.find_all("div", class_="g"):
        a_tag = g.find("a")
        if a_tag and "href" in a_tag.attrs:
            links.append(a_tag["href"])

    return page_source, links


# --------------------------------------------------------------------
# 5) Search route: usage check + scrape + upload to MinIO
# --------------------------------------------------------------------
@app.get("/search")
def search(request: Request, query: str):
    """
    1) Check the user's API key in header: x-api-key
    2) Enforce daily usage limit
    3) Scrape Google
    4) Upload the raw HTML to MinIO
    5) Return the links + presigned URL
    """
    # 5a) Validate the user's API key
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key.")

    # 5b) Get user record from Firebase
    users_ref = get_users_ref()
    user_data = users_ref.child(api_key).get()
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid API key.")

    usage_count = user_data.get("usage_count", 0)
    last_reset = user_data.get("last_reset")

    # 5c) Reset usage if new day
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if not last_reset or last_reset != today_str:
        usage_count = 0
        users_ref.child(api_key).update({"usage_count": usage_count, "last_reset": today_str})

    # 5d) Check daily limit
    if usage_count >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Daily limit reached. Upgrade or wait until tomorrow.")

    # 5e) Increment usage
    usage_count += 1
    users_ref.child(api_key).update({"usage_count": usage_count})

    # 5f) Scrape
    page_source, links = scrape_google(query)

    # 5g) Upload the entire HTML to MinIO, get a presigned URL
    presigned_url = upload_html_to_minio(page_source)

    # 5h) Return the results + URL
    return {
        "api_key": api_key,
        "usage_count": usage_count,
        "found_links": links,
        "html_presigned_url": presigned_url
    }
