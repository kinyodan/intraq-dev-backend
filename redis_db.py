from upstash_redis import Redis
import os

UPSTASH_TOKEN=os.getenv("UPSTASH_TOKEN",None)
UPSTASH_DB_URL=os.getenv("UPSTASH_DB_URL",None)

redis = Redis(url=UPSTASH_DB_URL , token=UPSTASH_TOKEN)

def init_redis_db():
	try:
		return redis
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Error In init_redis_db: {e}")
