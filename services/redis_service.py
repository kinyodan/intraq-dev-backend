import json
from datetime import datetime
from redis_db import init_redis_db
import json
from datetime import datetime

REDIS_DB = init_redis_db() if init_redis_db is not None else None

async def save_email_to_redis(client_id: str, email_data: dict):
    if not REDIS_DB:
        print("❌ Redis not connected")
        return False

    try:
        # email_key = f"client:{client_id}:emails:{email_data.get('from', 'unknown')}:{email_data["email_id"]}"
        email_key = f"client:{client_id}:email:{email_data['email_id']}"

        # Prepare clean data
        clean_data = {}
        for key, value in email_data.items():
            if isinstance(value, (dict, list)):
                clean_data[key] = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                clean_data[key] = value.isoformat()
            else:
                clean_data[key] = str(value)

        clean_data["saved_at"] = datetime.utcnow().isoformat()

        # ✅ Correct syntax for older redis-py (v4 and below)
        for field, value in clean_data.items():
            REDIS_DB.hset(email_key, field, value)

        result = await get_emails_sync(f"client:{client_id}:email")
        print(f"✅ Email saved successfully to Redis → {email_key}")
        return json.dump(result)

    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return False


async def get_emails_sync(key: str):
    emails = REDIS_DB.hgetall(key)
    if not emails:
        return {"data": False}

    return emails 

