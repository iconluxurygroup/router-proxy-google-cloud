from fastapi import FastAPI, HTTPException,Query
from pydantic import BaseModel
import httpx
import os,asyncio
import random,subprocess,time,uvicorn
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
    return {"status": "up",
        "device_id": DEVICE_ID }

@app.post("/fetch")
async def fetch_query(request: URLRequest):
    result = await fetch_any_url(request.url)
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
                return {"status": "Google is reachable", "public_ip": public_ip,
        "device_id": DEVICE_ID }
            else:
                return {"status": "Google is reachable but returned a non-OK status", "code": response.status_code, "public_ip": public_ip,
        "device_id": DEVICE_ID }
    except Exception as e:
        return {"status": "Failed to reach Google", "error": str(e), "public_ip": public_ip,
        "device_id": DEVICE_ID }

async def run_shell_command_async(command):
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return {
        "stdout": stdout.decode().strip(),
        "stderr": stderr.decode().strip(),
        "returncode": process.returncode
    }

async def reset_ip_vpn():
    process = await asyncio.create_subprocess_exec(
        "expressvpn", "disconnect",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    await asyncio.sleep(5)

    process = await asyncio.create_subprocess_exec(
        "expressvpn", "connect", "smart",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    await asyncio.sleep(5)


@app.get("/reset-ip")
async def reset_ip():
    try:
        await reset_ip_vpn()
        public_ip = await fetch_public_ip()
        ip_info = await fetch_ip_info(public_ip)
        return {
            "public_ip": public_ip,
            "ip_info": ip_info,
            "device_id": DEVICE_ID
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset IP: {e}")

    
async def get_vpn_status():
    result = subprocess.run(["expressvpn", "status"], capture_output=True, text=True)
    if "Not connected" in result.stdout:
        return "Not Connected"
    if "Connected to" in result.stdout:
        return "Connected"
    return "Unknown"


@app.get("/vpn-status")
async def vpn_status():
    status = await get_vpn_status()
    return {
        "vpn_status": status,
        "device_id": DEVICE_ID
    }


if __name__ == "__main__":
    uvicorn.run("app:app", port=8080, log_level="info",host='0.0.0.0')