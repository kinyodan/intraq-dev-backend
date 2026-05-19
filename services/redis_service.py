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
        # Create the Redis key
        email_key = f"client:{client_id}:emails:{email_data.get('from', 'unknown')}"

        # Prepare data (convert complex types to strings)
        clean_data = {}
        for key, value in email_data.items():
            if isinstance(value, (dict, list)):
                clean_data[key] = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                clean_data[key] = value.isoformat()
            else:
                clean_data[key] = str(value)

        clean_data["saved_at"] = datetime.utcnow().isoformat()

        # ✅ Correct hset syntax for Redis 5.x
        REDIS_DB.hset(
            email_key,           # This is the Redis key (no 'name=')
            mapping=clean_data   # Use 'mapping' instead of kwargs
        )

        print(f"✅ Email saved successfully to Redis → {email_key}")
        return True

    except Exception as e:
        print(f"❌ Failed to save email to Redis: {e}")
        return False