import os  



TELEGRAM_TOKEN = os.getenv(TELEGRAM_TOKEN, None)

CHAT_ID = "1541881597"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

async def send_telegram_msg(message):

    if !TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN is required")

    async with httpx.AsyncClient() as client:
        payload = {"chat_id": CHAT_ID, "text": message}
        await client.post(TELEGRAM_URL, json=payload)