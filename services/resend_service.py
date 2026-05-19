import resend
import os
import requests
import httpx
from typing import Optional, Dict

resend.api_key = os.getenv("RESEND_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")


async def get_full_email(email_id: str) -> Optional[Dict]:
    """Fetch full email content from Resend"""
    if not RESEND_API_KEY:
        print("❌ RESEND_API_KEY not found")
        return None

    try:
        url = f"https://api.resend.com/emails/receiving/{email_id}"
        
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                email_data = response.json()
                print(f"✅ Full email fetched: {email_data.get('subject')}")
                return email_data
            else:
                print(f"❌ Resend API Error {response.status_code}: {response.text}")
                return None

    except Exception as e:
        print(f"❌ Error fetching full email: {e}")
        return None        