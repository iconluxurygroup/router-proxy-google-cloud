# main.py
import os
import functions_framework
import httpx
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retrieve DEVICE_ID and HEADERSURL from environment variables with defaults
DEVICE_ID = os.getenv("DEVICE_ID", "G-CLOUD-DEFAULT")
HEADERSURL = os.getenv("HEADERSURL", "https://raw.githubusercontent.com/nikiconluxury/image-ip-mask-serverless/main/user-agent-list.json")

# Helper functions
def fetch_desktop_user_agent(url: str):
    """Fetch a random desktop user agent from the provided URL."""
    logger.info(f"Fetching user agent from {url}")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            response.raise_for_status()
            data = response.json()
            desktop_user_agents = data.get("UserAgents", {}).get("Desktop", [])
            if desktop_user_agents:
                return random.choice(desktop_user_agents)
            else:
                raise ValueError("No desktop user agents found")
    except Exception as e:
        logger.error(f"Failed to fetch user agent: {str(e)}")
        raise

def fetch_public_ip():
    """Fetch the public IP address of the function."""
    logger.info("Fetching public IP")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get("https://api.ipify.org?format=json")
            response.raise_for_status()
            return response.json().get("ip")
    except Exception as e:
        logger.error(f"Failed to fetch public IP: {str(e)}")
        raise

def fetch_ip_info(ip_address: str):
    """Fetch detailed information about an IP address."""
    logger.info(f"Fetching IP info for {ip_address}")
    try:
        url = f"http://ip-api.com/json/{ip_address}"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch IP info: {str(e)}")
        raise

def fetch_any_url(url: str):
    """Fetch content from any URL, using a random desktop user agent."""
    logger.info(f"Fetching URL: {url}")
    try:
        user_agent = fetch_desktop_user_agent(HEADERSURL)
        headers = {"User-Agent": user_agent} if user_agent else {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        with httpx.Client(follow_redirects=True, timeout=10.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"Failed to fetch URL: {str(e)}")
        raise

# Main Cloud Function handler
@functions_framework.http
def main(request):
    """Handle HTTP requests and route them to the appropriate endpoint logic."""
    logger.info(f"Received request: {request.method} {request.path}")
    path = request.path
    
    # Define CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",  # Wildcard for testing; restrict later
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    # Handle OPTIONS preflight requests
    if request.method == "OPTIONS":
        return "", 204, cors_headers

    # Process the request
    if path == "/health":
        logger.info("Health endpoint called")
        response = {"status": "up", "device_id": DEVICE_ID}
        return response, 200, cors_headers
    elif path == "/fetch" and request.method == "POST":
        logger.info("Fetch endpoint called")
        try:
            request_json = request.get_json()
            if not request_json or "url" not in request_json:
                return {"detail": "Missing 'url' in request body"}, 400, cors_headers
            url = request_json["url"]
            result = fetch_any_url(url)
            public_ip = fetch_public_ip()
            response = {"result": result, "public_ip": public_ip, "device_id": DEVICE_ID}
            return response, 200, cors_headers
        except Exception as e:
            logger.error(f"Fetch endpoint failed: {str(e)}")
            return {"detail": str(e)}, 500, cors_headers
    elif path == "/get-ip":
        logger.info("Get-ip endpoint called")
        try:
            public_ip = fetch_public_ip()
            ip_info = fetch_ip_info(public_ip)
            response = {"public_ip": public_ip, "ip_info": ip_info, "device_id": DEVICE_ID}
            return response, 200, cors_headers
        except Exception as e:
            logger.error(f"Get-ip endpoint failed: {str(e)}")
            return {"detail": str(e)}, 500, cors_headers
    elif path == "/health/google":
        logger.info("Health/google endpoint called")
        try:
            public_ip = fetch_public_ip()
            with httpx.Client(timeout=10.0) as client:
                logger.info("Attempting to reach Google")
                response = client.get("https://www.google.com")
                if response.status_code == 200:
                    status = "Google is reachable"
                else:
                    status = f"Google is reachable but returned a non-OK status: {response.status_code}"
        except Exception as e:
            logger.error(f"Health check to Google failed: {str(e)}")
            status = f"Failed to reach Google: {str(e)}"
        response = {"status": status, "public_ip": public_ip, "device_id": DEVICE_ID}
        return response, 200, cors_headers
    elif path == "/favicon.ico":
        logger.info("Favicon requested")
        return "", 204, cors_headers
    else:
        logger.info(f"Path not found: {path}")
        return {"detail": "Not Found"}, 404, cors_headers