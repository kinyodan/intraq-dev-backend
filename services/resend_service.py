import resend
import os
import requests

resend.api_key = os.getenv("RESEND_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

def get_full_email_sync(email_id: str):
    url = f"https://api.resend.com/emails/receiving/{email_id}"
    
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
    }

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None