from core.imports import *
from fastapi import APIRouter

router = APIRouter()

@router.get("/webhook")
async def verify_webhook(
    mode: str, 
    challenge: str,
    token: str,
    current_user: dict = Depends(get_current_user)
):
    """Verification handshake with Meta"""
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    return JSONResponse(status_code=403, content={"error": "Invalid token"})

@router.post("/webhook")
async def receive_message(request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Receives messages from WhatsApp Cloud API"""
    data = await request.json()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                messages = change.get("value", {}).get("messages", [])
                for msg in messages:
                    phone = msg["from"]
                    text = msg.get("text", {}).get("body", "")
                    process_onboarding(phone, text)
    except Exception as e:
        print("Webhook error:", e)
    return {"status": "ok"}
