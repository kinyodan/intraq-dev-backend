import os  
import sys

# Try to import httpx, handle if not available
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("WARNING: httpx not available, telegram notifications disabled")


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", None)

CHAT_ID = "1541881597"

import httpx

async def send_telegram_msg(message):
    print("🚀 Starting Sending telegram message")

    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set, skipping")
        return

    if not HTTPX_AVAILABLE:
        print("❌ httpx not available, skipping")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": str(message),
        "parse_mode": "HTML"
    }

    print(f"📡 Sending to Telegram: {url}")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)

        print(f"📨 Telegram status: {resp.status_code}")
        print(f"📨 Telegram response: {resp.text}")

        if resp.status_code != 200:
            print("❌ Telegram API failed")

    except Exception as e:
        print(f"❌ Failed to send telegram message: {e}")