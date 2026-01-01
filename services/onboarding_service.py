# services/onboarding_service.py (or wherever your function lives)

from db import SessionLocal  # This gives you the scoped_session
from models import Client      # Make sure your Client model is imported
from services.whatsapp_service import send_message

def process_onboarding(phone: str, message: str):
    """Handle new client onboarding requests via WhatsApp message"""
    
    # Normalize and check message format
    message_lower = message.strip().lower()
    if not message_lower.startswith("onboard:"):
        return  # Not an onboarding request

    # Extract client_code safely
    try:
        client_code = message.split(":", 1)[1].strip()
        if not client_code:
            send_message(phone, "❌ Invalid format. Please send: onboard:YOUR_CLIENT_ID")
            return
    except IndexError:
        send_message(phone, "❌ Invalid format. Please send: onboard:YOUR_CLIENT_ID")
        return

    # Get a thread-safe DB session
    db = SessionLocal()
    try:
        # Check if client already exists
        client = db.query(Client).filter(Client.id == client_code).first()

        if client:
            # Already exists
            if client.onboarded:
                send_message(phone, f"✅ You’re already onboarded to Intraq (Client ID: {client.id}).")
            else:
                # Exists but not onboarded yet (rare case) – update it
                client.phone_number = phone
                client.onboarded = True
                db.commit()
                send_message(phone, f"✅ Onboarding completed successfully (Client ID: {client.id}).")
        else:
            # New client – create and save
            new_client = Client(
                id=client_code,
                phone_number=phone,
                onboarded=True
            )
            db.add(new_client)
            db.commit()
            send_message(phone, f"✅ You’ve been onboarded successfully to Intraq (Client ID: {client_code}).")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Onboarding failed for {phone}: {e}")
        send_message(phone, "❌ Something went wrong during onboarding. Please try again later.")

    finally:
        # Important: remove the session from the scoped thread
        SessionLocal.remove()  # This replaces db.close() when using scoped_session