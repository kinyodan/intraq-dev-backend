from upstash_redis import Redis

redis = Redis(url=UPSTASH_DB_URL , token=UPSTASH_TOKEN)

def init_redis_db():
	try:
		return redis
    except Exception as e:
    	raise HTTPException(status_code=500, detail=f"Error In init_redis_db: {e}")
