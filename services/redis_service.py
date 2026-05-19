import json
from datetime import datetime
from redis_db import init_redis_db

REDIS_DB = init_redis_db || None

async def save_email_to_redis(client_id: str, email_data: dict):

    if not REDIS_DB:
        print(f"❌ Error initializing Redis DB ")
        return False

    try:
        email_key = f"clients:{client_id}:emails:{email_data.get('from', 'unknown')}"
        
        # Clean and prepare data
        email_data["saved_at"] = datetime.utcnow().isoformat()
        
        REDIS_DB.hset(
            name=email_key,
            mapping={
                "from": email_data.get("from"),
                "subject": email_data.get("subject"),
                "text": email_data.get("text"),
                "html": email_data.get("html"),
                "received_at": email_data.get("received_at"),
                "full_data": json.dumps(email_data, default=str)
            }
        )
        
        print(f"✅ Email saved to Redis: {email_key}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return False