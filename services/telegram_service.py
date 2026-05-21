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

async def send_telegram_msg(message):
    print( "Starting Sending telegram message ")
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not set, skipping telegram notification")
        return
    
    if not HTTPX_AVAILABLE:
        print("httpx not available, skipping telegram notification")
        return
    
    TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    print( f"Sending telegram message to {TELEGRAM_URL}")

    try:
        async with httpx.AsyncClient() as client:
            payload = {"chat_id": CHAT_ID, "text": str(message)}
            await client.post(TELEGRAM_URL, json=payload)
    except Exception as e:
        print(f"Failed to send telegram message: {e}")