import os  
import sys
import html
import httpx

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
    print("🚀 Starting Sending telegram message")

    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set, skipping")
        return

    if not HTTPX_AVAILABLE:
        print("❌ httpx not available, skipping")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    normalized_message = {
        "email_id": message.get("email_id"),
        "from": message.get("from"),
        "to": message.get("to"),
        "subject": message.get("subject"),
        "received_at": message.get("received_at"),
        "attachments": message.get("attachments", [])
    }

    sender = html.escape(str(normalized_message.get("from", "Unknown")))
    recipients = html.escape(str(normalized_message.get("to", "Unknown")))
    subject = html.escape(str(normalized_message.get("subject", "No Subject")))
    email_id = html.escape(str(normalized_message.get("email_id", "N/A")))
    received_at = html.escape(str(normalized_message.get("received_at", "Unknown")))

    attachments = normalized_message.get("attachments", [])
    attachment_count = len(attachments) if attachments else 0

    telegram_message = f"""
📩 <b>New Inbound Email</b>

━━━━━━━━━━━━━━━━━━

👤 <b>From</b>
{sender}

📬 <b>To</b>
{recipients}

📝 <b>Subject</b>
{subject}

📎 <b>Attachments</b>
{attachment_count}

🕒 <b>Received</b>
{received_at}

🆔 <b>Email ID</b>
<code>{email_id}</code>

━━━━━━━━━━━━━━━━━━
<b>INTRAQ</b> • Email Operations
"""

    payload = {
        "chat_id": CHAT_ID,
        "text": telegram_message,
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



# async def send_telegram_msg(message):
#     print("🚀 Starting Sending telegram message")

#     if not TELEGRAM_TOKEN:
#         print("❌ TELEGRAM_TOKEN not set, skipping")
#         return

#     if not HTTPX_AVAILABLE:
#         print("❌ httpx not available, skipping")
#         return

#     url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

#     normalized_message = {
#         "email_id": message.get("email_id"),
#         "from": message.get("from"),
#         "to": message.get("to"),
#         "subject": message.get("subject"),
#         "received_at": data.get("created_at"),
#         "attachments": data.get("attachments", [])
#     }

#     payload = {
#         "chat_id": CHAT_ID,
#         "text": str(message),
#         "parse_mode": "HTML"
#     }

#     print(f"📡 Sending to Telegram: {url}")

#     try:
#         async with httpx.AsyncClient(timeout=10) as client:
#             resp = await client.post(url, json=payload)

#         print(f"📨 Telegram status: {resp.status_code}")
#         print(f"📨 Telegram response: {resp.text}")

#         if resp.status_code != 200:
#             print("❌ Telegram API failed")

#     except Exception as e:
#         print(f"❌ Failed to send telegram message: {e}")
