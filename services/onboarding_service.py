from db.models import Client, SessionLocal
from services.whatsapp_service import send_message

def process_onboarding(phone: str, message: str):
    """Handle new client onboarding requests"""
    db = SessionLocal()
    try:
        if not message.startswith("onboard:"):
            return

        client_code = message.split(":")[1].strip()
        client = db.query(Client).filter(Client.id == client_code).first()

        if not client:
            # Register a new client entry
            client = Client(id=client_code, phone_number=phone, onboarded=True)
            db.add(client)
            db.commit()
            send_message(phone, f"✅ You’ve been onboarded successfully to Intraq (Client ID: {client_code}).")
        else:
            send_message(phone, f"✅ You’re already onboarded to Intraq (Client ID: {client.id}).")
    finally:
        db.close()
