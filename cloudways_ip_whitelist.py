import os
import logging
import asyncio
import aiohttp
import sys
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whitelist_ip.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Load environment variables
load_dotenv()

# Cloudways API configuration
CLOUDWAYS_CONFIG = {
    'email': os.getenv("CLOUDWAYS_EMAIL"),
    'api_key': os.getenv("CLOUDWAYS_API_KEY"),
    'server_id': os.getenv("CLOUDWAYS_SERVER_ID"),
}

async def get_cloudways_access_token(session):
    """Obtains an access token from the Cloudways API."""
    url = "https://api.cloudways.com/api/v1/oauth/access_token"
    data = {
        "email": CLOUDWAYS_CONFIG["email"],
        "api_key": CLOUDWAYS_CONFIG["api_key"]
    }

    try:
        async with session.post(url, json=data) as response:
            response.raise_for_status()
            result = await response.json()
            return result.get('access_token')
    except Exception as e:
        logging.error(f"Failed to obtain Cloudways access token: {e}")
        return None

async def get_current_ip(session):
    """Fetches the current public IP address."""
    try:
        async with session.get('https://api.ipify.org') as response:
            response.raise_for_status()
            ip_address = await response.text()
            return ip_address
    except Exception as e:
        logging.error(f"Failed to fetch current IP: {e}")
        return None

async def whitelist_current_ip(session):
    """Adds the current IP to the Cloudways whitelist using the Cloudways API."""
    current_ip = await get_current_ip(session)
    if not current_ip:
        logging.error("Failed to obtain current IP address")
        return False

    access_token = await get_cloudways_access_token(session)
    if not access_token:
        logging.error("Failed to obtain Cloudways access token")
        return False

    url = "https://api.cloudways.com/api/v1/security/whitelisted"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        "server_id": CLOUDWAYS_CONFIG["server_id"],
        "ipPolicy": "allow_all",
        "tab": "mysql",
        "ip[]": current_ip,
        "type": "mysql"
    }

    try:
        async with session.post(url, data=data, headers=headers) as response:
            response.raise_for_status()
            logging.info(f"Successfully whitelisted IP: {current_ip}")
            return True
    except Exception as e:
        logging.error(f"Failed to whitelist IP: {e}")
        return False

def whitelist_ip_sync():
    """Synchronous wrapper for the async IP whitelisting function."""
    try:
        logging.info("Starting IP whitelisting process")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_whitelist():
            async with aiohttp.ClientSession() as session:
                return await whitelist_current_ip(session)
        
        result = loop.run_until_complete(run_whitelist())
        loop.close()
        
        if result:
            logging.info("Successfully whitelisted IP for database access")
        else:
            logging.error("Failed to whitelist IP for database access")
            
        return result
    except Exception as e:
        logging.error(f"Error in whitelist_ip_sync: {e}")
        return False

# Main execution
if __name__ == "__main__":
    # Check for required environment variables
    required_vars = ["CLOUDWAYS_EMAIL", "CLOUDWAYS_API_KEY", "CLOUDWAYS_SERVER_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing environment variables: {', '.join(missing_vars)}")
        print("Please make sure these variables are set in your .env file.")
        sys.exit(1)
    
    # Run the IP whitelisting
    if whitelist_ip_sync():
        print("IP whitelisting successful!")
    else:
        print("IP whitelisting failed. Check the logs for details.")