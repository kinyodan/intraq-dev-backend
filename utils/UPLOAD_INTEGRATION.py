"""
Example: How to integrate the new Data Processing Service into upload_service.py

Add these modifications to your existing upload_service.py file
"""

# ============================================
# STEP 1: Add this import at the top
# ============================================

# Add this with your other imports
from services.dfe_automation_service import (
    data_processing_service,
    quick_clean_upload,
    run_enrichment_background
)


# ============================================
# STEP 2: Modify handle_upload function
# ============================================

def handle_upload(
    file_obj,           # bytes
    filename: str,
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code=False,
    processing_errors={}):
    """
    MODIFIED VERSION with Two-Phase Processing
    
    Phase 1 (Synchronous): Quick Clean - runs immediately
    Phase 2 (Asynchronous): Enrichment - runs as background job
    """
    print(f"📁 handle_upload called for: {filename}")
   
    try:
        content = file_obj
        df = read_file_bytes(filename, content)
        print(f"✅ DataFrame loaded: {df.shape}")
       
        if df.empty:
            print("⚠️ Warning: DataFrame is empty!")
            return {"error": "Empty dataframe", "filename": filename}
       
        # ═══════════════════════════════════════════════════════
        # PHASE 1: QUICK CLEAN (Synchronous - before saving)
        # ═══════════════════════════════════════════════════════
        print("🧹 Phase 1: Running quick clean...")
        df = quick_clean_upload(df)  # <-- NEW LINE
        print(f"✅ Quick clean complete. {len(df)} records cleaned")
        
        # Track how many records had invalid phones
        invalid_phone_count = (~df.get('_phone_valid', True)).sum() if '_phone_valid' in df.columns else 0
        if invalid_phone_count > 0:
            print(f"⚠️ {invalid_phone_count} records have invalid phone numbers")
       
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        dataset_id = str(uuid.uuid4())
        table_name = f"client_{client_id}_data_{dataset_id.replace('-', '_')}"
       
        print(f"📝 Dataset ID: {dataset_id}")
        print(f"🗄️ Table name: {table_name}")

        # ═══════════════════════════════════════════════════════
        # UPLOAD TO CLOUDINARY (backup of original file)
        # ═══════════════════════════════════════════════════════
        print("☁️ Uploading file to Cloudinary...")
        
        folder_path = f"intraq-uploads/client_{client_id}/{dataset_id}"
        
        upload_result = cloudinary.uploader.upload(
            file_obj,
            resource_type="auto",
            public_id=f"{dataset_id}_{filename.split('.')[0]}",
            folder=folder_path,
            overwrite=True
        )
        
        cloudinary_url = upload_result['secure_url']
        cloudinary_public_id = upload_result['public_id']
        
        print(f"✅ File uploaded to Cloudinary: {cloudinary_url}")

        # ═══════════════════════════════════════════════════════
        # SAVE CLEANED DATA TO DATABASE
        # ═══════════════════════════════════════════════════════
        print("💿 Saving cleaned data to database...")
        save_dataframe_as_table(df, table_name)

        # Infer schema
        schema = infer_schema(df)

        # Save metadata with processing status
        ds = store_metadata(
            client_id=client_id,
            project_name=project_name,
            project_code=project_code,
            processing_errors=processing_errors,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            dataset_id=dataset_id,
            table_name=table_name,
            filename=filename,
            schema=schema,
            row_count=len(df),
            meta={
                "rows": len(df),
                "cloudinary_url": cloudinary_url,
                "cloudinary_public_id": cloudinary_public_id,
                "quick_cleaned": True,
                "cleaned_at": datetime.utcnow().isoformat(),
                "invalid_phones": int(invalid_phone_count),
                "enrichment_status": "pending"  # Will be updated after background job
            }
        )

        print(f"✅ handle_upload completed successfully")
        
        # ═══════════════════════════════════════════════════════
        # RETURN RESULT (enrichment happens in background)
        # ═══════════════════════════════════════════════════════
        return {
            "dataset_id": dataset_id,
            "project_name": project_name,
            "project_code": project_code,
            "processing_errors": processing_errors,
            "assigned_to": assigned_to,
            "assigned_by": assigned_by,
            "table_name": table_name,
            "filename": filename,
            "rows": len(df),
            "schema": schema,
            "cloudinary_url": cloudinary_url,
            "cleaned": True,
            "invalid_phone_count": int(invalid_phone_count),
            "enrichment_status": "queued"  # Tell client enrichment is coming
        }
       
    except Exception as e:
        print(f"❌ Error in handle_upload: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================
# STEP 3: Add this endpoint to main.py
# ============================================

"""
Add these imports to main.py:

from services.dfe_automation_service import (
    data_processing_service,
    run_enrichment_background
)
"""

# Modified upload endpoint with enrichment queueing
@app.post("/api/datasets/upload")
async def upload_dataset(
    background_tasks: BackgroundTasks,  # <-- Add this parameter
    file: UploadFile = File(...),
    project_name: str = Form(...),
    project_code: str = Form(...),
    client_id: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload dataset with two-phase processing:
    1. Quick Clean (synchronous) - names, phones, IDs
    2. Enrichment (asynchronous) - GPS, locations, file splitting
    """
    # Validate access
    if not data_processing_service.validate_client_access(current_user, client_id):
        raise HTTPException(403, "Access denied for this client")
    
    # Read file
    content = await file.read()
    
    # Process upload (includes quick clean)
    result = handle_upload(
        file_obj=content,
        filename=file.filename,
        project_name=project_name,
        project_code=project_code,
        client_id=client_id,
        assigned_to=current_user.get("name", "Unknown"),
        assigned_by=current_user.get("name", "Unknown")
    )
    
    if "error" in result:
        raise HTTPException(400, result["error"])
    
    # ═══════════════════════════════════════════════════════
    # QUEUE ENRICHMENT AS BACKGROUND JOB
    # ═══════════════════════════════════════════════════════
    background_tasks.add_task(
        run_enrichment_background,
        client_id=client_id,
        table_name=result["table_name"],
        dataset_id=result["dataset_id"],
        user_id=current_user.get("sub")
    )
    
    print(f"🚀 Enrichment queued for dataset {result['dataset_id']}")
    
    return {
        **result,
        "message": "File uploaded and cleaned successfully. Enrichment is processing in the background.",
        "enrichment_status": "queued"
    }


# ============================================
# STEP 4: Add status checking endpoints
# ============================================

@app.get("/api/datasets/{dataset_id}/processing-status")
async def get_processing_status(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get the processing status of a dataset
    
    Returns:
        - quick_cleaned: True (always true after upload)
        - enrichment_status: pending/running/completed/failed
        - output_files: List of generated files (if enrichment complete)
    """
    from db import SessionLocal
    from models import Dataset
    
    db = SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        
        if not dataset:
            raise HTTPException(404, "Dataset not found")
        
        # Check access
        if not data_processing_service.validate_client_access(current_user, dataset.client_id):
            raise HTTPException(403, "Access denied")
        
        # Parse metadata
        import json
        meta = json.loads(dataset.meta) if dataset.meta else {}
        
        return {
            "dataset_id": dataset_id,
            "table_name": dataset.table_name,
            "row_count": dataset.schema.get("row_count") if dataset.schema else None,
            "quick_cleaned": meta.get("quick_cleaned", True),
            "cleaned_at": meta.get("cleaned_at"),
            "enrichment_status": meta.get("enrichment_status", "unknown"),
            "enriched_at": meta.get("enriched_at"),
            "output_files": meta.get("output_files", []),
            "invalid_phone_count": meta.get("invalid_phones", 0),
            "cloudinary_url": meta.get("cloudinary_url")
        }
    finally:
        db.close()


@app.get("/api/datasets/{dataset_id}/output-files")
async def get_output_files(
    dataset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of processed output files for a dataset
    (CAW-split files created after enrichment)
    """
    from db import SessionLocal
    from models import Dataset
    import json
    
    db = SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        
        if not dataset:
            raise HTTPException(404, "Dataset not found")
        
        # Check access
        if not data_processing_service.validate_client_access(current_user, dataset.client_id):
            raise HTTPException(403, "Access denied")
        
        meta = json.loads(dataset.meta) if dataset.meta else {}
        output_files = meta.get("output_files", [])
        
        # Get file details
        files_info = []
        for filepath in output_files:
            if os.path.exists(filepath):
                stats = os.stat(filepath)
                files_info.append({
                    "filename": os.path.basename(filepath),
                    "path": filepath,
                    "size_bytes": stats.st_size,
                    "size_mb": round(stats.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stats.st_ctime).isoformat()
                })
        
        return {
            "dataset_id": dataset_id,
            "enrichment_complete": meta.get("enrichment_status") == "completed",
            "files": files_info,
            "total_files": len(files_info)
        }
    finally:
        db.close()


@app.get("/api/enrichment/jobs")
async def list_enrichment_jobs(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    List active enrichment jobs
    """
    # Filter by access
    if client_id and not data_processing_service.validate_client_access(current_user, client_id):
        raise HTTPException(403, "Access denied for this client")
    
    # Get jobs
    if client_id:
        jobs = data_processing_service.list_active_jobs(client_id)
    else:
        # Only show jobs for accessible clients
        all_jobs = data_processing_service.list_active_jobs()
        jobs = [
            job for job in all_jobs
            if data_processing_service.validate_client_access(current_user, job.get("client_id"))
        ]
    
    return {
        "jobs": jobs,
        "total": len(jobs)
    }


# ============================================
# STEP 5: Optional - WebSocket for real-time updates
# ============================================

from fastapi import WebSocket

@app.websocket("/ws/enrichment/{dataset_id}")
async def enrichment_websocket(websocket: WebSocket, dataset_id: str):
    """
    WebSocket endpoint for real-time enrichment progress updates
    
    Frontend usage:
        const ws = new WebSocket(`ws://your-api/ws/enrichment/${datasetId}`);
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log("Status:", data.status);
        };
    """
    await websocket.accept()
    
    import asyncio
    last_status = None
    
    try:
        while True:
            # Check dataset status
            from db import SessionLocal
            from models import Dataset
            import json
            
            db = SessionLocal()
            try:
                dataset = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
                if dataset and dataset.meta:
                    meta = json.loads(dataset.meta)
                    status = meta.get("enrichment_status")
                    
                    if status != last_status:
                        await websocket.send_json({
                            "dataset_id": dataset_id,
                            "status": status,
                            "enriched_at": meta.get("enriched_at"),
                            "output_files": len(meta.get("output_files", []))
                        })
                        last_status = status
                    
                    # Close if complete or failed
                    if status in ["completed", "failed"]:
                        break
            finally:
                db.close()
            
            await asyncio.sleep(2)  # Poll every 2 seconds
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# ============================================
# STEP 6: Celery Alternative (if you prefer Celery over BackgroundTasks)
# ============================================

"""
If using Celery instead of BackgroundTasks:

# In your celery configuration:
from services.dfe_automation_service import create_celery_tasks

process_enrichment_task = create_celery_tasks(celery_app)

# Then in your upload endpoint:
@app.post("/api/datasets/upload-celery")
async def upload_with_celery(file, ...):
    result = handle_upload(...)
    
    # Queue Celery task
    task = process_enrichment_task.delay(
        client_id=client_id,
        table_name=result["table_name"],
        dataset_id=result["dataset_id"],
        user_id=current_user.get("sub")
    )
    
    return {
        **result,
        "task_id": task.id,
        "enrichment_status": "queued_via_celery"
    }
"""
