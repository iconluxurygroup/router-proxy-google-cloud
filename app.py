from fastapi import FastAPI, HTTPException,Query
from pydantic import BaseModel
import httpx
import os
import random,urllib
from dotenv import load_dotenv

DEVICE_ID = "G-CLOUD-0001"

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

class URLRequest(BaseModel):
    url: str

async def fetch_desktop_user_agent(url: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.3'})
            data = response.json()
            desktop_user_agents = data.get("UserAgents", {}).get("Desktop", [])
            return random.choice(desktop_user_agents) if desktop_user_agents else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user agents: {str(e)}")

async def fetch_public_ip():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get('https://api.ipify.org?format=json', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.3'})
            data = response.json()
            return data.get("ip")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch public IP: {str(e)}")

async def fetch_ip_info(ip_address: str):
    url = f"http://ip-api.com/json/{ip_address}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch IP information")

async def fetch_any_url(url: str):
    try:
        # Ensure the user agent function call is awaited
        user_agent = await fetch_desktop_user_agent(os.getenv("HEADERSURL", ''))
        headers = {'User-Agent': user_agent} if user_agent else {}
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            return response.text
    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}

@app.get("/health")
async def health_check():
    return {"status": "up", "device_id": DEVICE_ID }

@app.post("/fetch")
async def fetch_query(url: str = Query(None, description="URL to fetch")):
    encoded_url = urllib.parse.quote(url, safe='')
    result = await fetch_any_url(encoded_url)
    public_ip = await fetch_public_ip()
    # Return the result along with the device ID and public IP
    return {
        "result": result,
        "public_ip": public_ip,
        "device_id": DEVICE_ID 
    }

@app.get("/get-ip")
async def get_public_ip():
    public_ip = await fetch_public_ip()
    if public_ip:
        ip_info = await fetch_ip_info(public_ip)
        return {
            "public_ip": public_ip,
            "ip_info": ip_info,
            "device_id": DEVICE_ID 
    }
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch public IP")

@app.get("/health/google")
async def health_check_google():
    public_ip = await fetch_public_ip()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.google.com")
            if response.status_code == 200:
                return {"status": "Google is reachable", "public_ip": public_ip}
            else:
                return {"status": "Google is reachable but returned a non-OK status", "code": response.status_code, "public_ip": public_ip}
    except Exception as e:
        return {"status": "Failed to reach Google", "error": str(e), "public_ip": public_ip}
