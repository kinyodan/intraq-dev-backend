"""
Example: How to integrate DFE Automation Service into main.py

Add these imports and endpoints to your existing main.py file
"""

# ============================================
# STEP 1: Add this import at the top of main.py
# ============================================

# Add this with your other service imports (around line 20)
from services.dfe_automation_service import (
    dfe_service, 
    run_dfe_automation_background,
    DFEAutomationService
)


# ============================================
# STEP 2: Add these Pydantic models for request/response
# ============================================

from pydantic import BaseModel
from typing import Optional

class DFEAutomationRequest(BaseModel):
    """Request model for DFE automation"""
    client_id: str
    input_file: Optional[str] = None  # Optional: specific file to process
    split_by: str = "caw"  # How to split files: 'caw', 'center', 'constituency'

class DFEAutomationResponse(BaseModel):
    """Response model for DFE automation"""
    job_id: str
    client_id: str
    status: str
    message: str
    files_processed: Optional[list] = None


# ============================================
# STEP 3: Add these endpoints to your FastAPI app
# ============================================

@app.post("/api/dfe/run-automation", response_model=DFEAutomationResponse)
async def run_dfe_automation(
    background_tasks: BackgroundTasks,
    client_id: str = Form(...),
    input_file: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Run DFE automation pipeline for a client.
    
    This endpoint:
    1. Validates that the current user has access to the client_id
    2. Queues the automation as a background job
    3. Returns immediately with a job_id for tracking
    
    The background job will:
    - Clean the CSV/Excel file
    - Normalize the data (names, phones, IDs, GPS, etc.)
    - Split files by CAW/constituency/polling center
    - Save results to ~/dev/dfe/normalized/
    
    Args:
        client_id: The client ID to process files for
        input_file: Optional specific file path to process (if None, processes all files for client)
    
    Returns:
        job_id: Use this to check job status via /api/dfe/job-status/{job_id}
    """
    
    # Validate client access
    if not dfe_service.validate_client_access(current_user, client_id):
        raise HTTPException(
            status_code=403, 
            detail=f"Access denied: You don't have permission to run automation for client {client_id}"
        )
    
    # Generate job ID
    job_id = f"dfe_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Queue background task
    background_tasks.add_task(
        run_dfe_automation_background,
        client_id=client_id,
        user_id=current_user.get("sub"),
        input_file=input_file
    )
    
    return DFEAutomationResponse(
        job_id=job_id,
        client_id=client_id,
        status="queued",
        message=f"DFE automation queued for client {client_id}. Job ID: {job_id}"
    )


@app.get("/api/dfe/job-status/{job_id}")
async def get_dfe_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get the status of a DFE automation job.
    
    Args:
        job_id: The job ID returned from /api/dfe/run-automation
        
    Returns:
        Job status including progress, files processed, and any errors
    """
    job_status = dfe_service.get_job_status(job_id)
    
    if not job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    # Verify user has access to this job
    if not dfe_service.validate_client_access(current_user, job_status.get("client_id")):
        raise HTTPException(status_code=403, detail="Access denied for this job")
    
    return {
        "job_id": job_id,
        **job_status
    }


@app.get("/api/dfe/active-jobs")
async def list_dfe_active_jobs(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    List all active/running DFE automation jobs.
    
    Args:
        client_id: Optional filter by client_id
        
    Returns:
        List of active jobs
    """
    # If client_id provided, validate access
    if client_id and not dfe_service.validate_client_access(current_user, client_id):
        raise HTTPException(status_code=403, detail="Access denied for this client")
    
    # If no client_id, only show jobs for accessible clients
    jobs = dfe_service.list_active_jobs(client_id)
    
    # Filter jobs by access (unless user is admin)
    accessible_jobs = [
        job for job in jobs 
        if dfe_service.validate_client_access(current_user, job.get("client_id"))
    ]
    
    return {
        "jobs": accessible_jobs,
        "total": len(accessible_jobs)
    }


@app.post("/api/dfe/process-pipeline")
async def run_dfe_pipeline(
    background_tasks: BackgroundTasks,
    input_file: str = Form(...),  # Path to file
    client_id: str = Form(...),
    split_by: str = Form("caw"),  # 'caw', 'center', 'constituency', 'rows'
    current_user: dict = Depends(get_current_user)
):
    """
    Run the complete DFE pipeline (Clean → Normalize → Split) on a specific file.
    
    This is useful for one-off file processing without running the full automation.
    
    Args:
        input_file: Path to the CSV/Excel file to process
        client_id: Client ID for validation
        split_by: How to split the output files ('caw', 'center', 'constituency')
    """
    
    # Validate access
    if not dfe_service.validate_client_access(current_user, client_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate file exists
    if not os.path.exists(input_file):
        raise HTTPException(status_code=404, detail=f"File not found: {input_file}")
    
    # Generate job ID
    job_id = f"dfe_pipeline_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def run_pipeline_task():
        """Background task to run pipeline"""
        try:
            result = dfe_service.process_file_pipeline(
                input_file=input_file,
                split_by=split_by
            )
            dfe_service._log(f"Pipeline completed for {input_file}: {result['status']}", job_id)
        except Exception as e:
            dfe_service._log(f"Pipeline failed: {e}", job_id)
    
    # Queue background task
    background_tasks.add_task(run_pipeline_task)
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Pipeline queued for {input_file}",
        "input_file": input_file,
        "split_by": split_by
    }


# ============================================
# STEP 4: Alternative Celery Integration (if you prefer Celery over BackgroundTasks)
# ============================================

# If you want to use Celery instead of BackgroundTasks, add this:

# from celery import Celery
# 
# @celery_app.task(bind=True, max_retries=3)
# def dfe_automation_celery_task(self, client_id: str, user_id: str = None, input_file: str = None):
#     """Celery task for DFE automation"""
#     try:
#         return dfe_service.run_automation_for_client(client_id, user_id, input_file)
#     except Exception as exc:
#         self.retry(exc=exc, countdown=2 ** self.request.retries)
#
# # Then in your endpoint:
# @app.post("/api/dfe/run-automation-celery")
# async def run_dfe_automation_celery(
#     client_id: str = Form(...),
#     input_file: Optional[str] = Form(None),
#     current_user: dict = Depends(get_current_user)
# ):
#     if not dfe_service.validate_client_access(current_user, client_id):
#         raise HTTPException(403, "Access denied")
#     
#     # Queue Celery task instead of BackgroundTasks
#     task = dfe_automation_celery_task.delay(client_id, current_user.get("sub"), input_file)
#     
#     return {
#         "task_id": task.id,
#         "status": "queued",
#         "message": "DFE automation queued via Celery"
#     }


# ============================================
# STEP 5: Add to your upload endpoint (optional - auto-trigger after upload)
# ============================================

# If you want to automatically trigger DFE processing after file upload,
# modify your upload_dataset endpoint:

# In your existing upload_dataset endpoint, after saving the file:
# 
# # Optional: Auto-trigger DFE pipeline if file matches criteria
# if filename.endswith(('.csv', '.xlsx', '.xls')):
#     background_tasks.add_task(
#         dfe_service.process_file_pipeline,
#         input_file=saved_file_path,
#         split_by='caw'
#     )
