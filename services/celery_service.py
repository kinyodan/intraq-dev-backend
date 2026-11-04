
celery_app = Celery(
    'tasks',
    broker=REDIS_DB,  # Message broker
    backend=REDIS_DB,  # Result backend
    broker_connection_retry_on_startup=True
)

# Optional: Configure Celery settings
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,
)



@celery_app.task(bind=True, max_retries=3)
def run_upload_task(
    self,
    file_content, 
    filename: str, 
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code=False,
    processing_errors={}
    ):
    
    print("=" * 50)
    print(f"🚀 CELERY TASK STARTED: {filename}")
    print(f"📦 File size: {len(file_content)} bytes")
    print(f"🏢 Project: {project_name}")
    print(f"👤 Client: {client_id}")
    print(f"🎯 Task ID: {self.request.id}")
    print("=" * 50)
    
    try:
        
        # Call your function
        result = handle_upload(
            file_content, 
            filename, 
            project_name,
            assigned_to,
            assigned_by,
            client_id,
            project_code,
            processing_errors or {}
        )
        
        print(f"✅ Task completed successfully!")
        print(f"📊 Result: {result}")
        print("=" * 50)
        
        return result
        
    except Exception as exc:
        print(f"❌ Task failed: {exc}")
        import traceback
        traceback.print_exc()
        
        # Retry with exponential backoff
        self.retry(exc=exc, countdown=2 ** self.request.retries)
