import os
import requests

GRAPH_API_URL = "https://graph.facebook.com/v17.0"
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")

def send_message(to: str, text: str):
    """Send a message via WhatsApp Cloud API"""
    url = f"{GRAPH_API_URL}/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.json()
