from core.imports import *
from fastapi import APIRouter

router = APIRouter()

class SoftDeleteRequest(BaseModel):
    reason: Optional[str] = None
    permanent_delete_days: int = 30

# ────────────────────────────────────────────────
#   Background function – still def (not async def)
# ────────────────────────────────────────────────
def run_upload_task_background(
    task_id: str,                   # ← new: your own ID
    file_content: bytes,
    filename: str,
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code: str,
    processing_errors: Dict = None
):
    processing_errors = processing_errors or {}

    print("=" * 60)
    print(f"🚀 BACKGROUND TASK STARTED       | Task ID: {task_id}")
    print(f"   File: {filename:<30} | Size: {len(file_content):,} bytes")
    print(f"   Project: {project_name} ({project_code})")
    print(f"   Client: {client_id}  | Assigned: {assigned_to}")
    print("=" * 60)

    start_time = datetime.utcnow()

    try:

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

        duration = (datetime.utcnow() - start_time).total_seconds()

        print(f"✅ TASK COMPLETED SUCCESSFULLY   | Task ID: {task_id}")
        print(f"   Duration: {duration:.2f} seconds")
        print(f"   Result: {result}")
        print("=" * 60)

        # Optional: update some status store
        # update_task_status(task_id, "success", result=result, duration=duration)

        return result  # ← return value is ignored by BackgroundTasks

    except Exception as exc:
        duration = (datetime.utcnow() - start_time).total_seconds()

        print(f"❌ TASK FAILED                    | Task ID: {task_id}")
        print(f"   Error: {exc}")
        print(f"   Duration: {duration:.2f} seconds")
        print("=" * 60)

        # Important: log somewhere persistent
        # log_error(task_id, filename, exc)
        # update_task_status(task_id, "failed", error=str(exc), duration=duration)

        raise   # ← re-raise if you want to see it in logs / sentry

# ────────────────────────────────────────────────
#               FIXED ENDPOINT
# ────────────────────────────────────────────────

ALLOWED_PRODUCTS = ("Voiceflow", "FileFlow", "MailFlow", "SyncFlow", "Apiflow")

# @app.post("/create_project", response_model=dict)
# async def create_project(
#     background_tasks: BackgroundTasks,
#     current_user: dict = Depends(get_current_user),
#     project_name: str = Form(...),
#     client_id: str = Form(...),
#     product: str = Form(...),
# ):

#     if project_type not in  ALLOWED_PRODUCTS:
#         raise HTTPException(400, "The Product does not exists")

#     if project_code == "null":
#         project_code = f"PRJ-{shortuuid.ShortUUID().random(length=8).upper()}"


@router.post("/edit_project", response_model=dict)
async def edit_project(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    client_id: str = Form(...),
    product: str = Form(...),
    current_user: dict = Depends(get_current_user),
):

    if project_code == "null":
        raise HTTPException(400, "No project_code present")

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Project edited ",
            "project_code": project_code,
        }
    )

@router.post("/delete_project", response_model=dict)
async def delete_project(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    client_id: str = Form(...),
    project_code: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    if not project_code:
        raise HTTPException(400, "No project_code present")

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Project deleted  ",
            "project_code": project_code,
            "project_name": project_name
        }
    )

@router.post("/create_project", response_model=dict)
async def create_project(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    client_id: str = Form(...),
    files: List[UploadFile] = File(...),
    assigned_to: str = Form(...),
    assigned_by: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    if project_code == "null":
        project_code = f"PRJ-{shortuuid.ShortUUID().random(length=8).upper()}"

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Project created  ",
            "project_code": project_code
        }
    )

@router.post("/upload_dataset", response_model=dict)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    client_id: str = Form(...),
    project_code: str = Form(...),
    files: List[UploadFile] = File(...),
    assigned_to: str = Form(...),
    assigned_by: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    if project_code == "null":
        raise HTTPException(400, "project_code is missing")


    datasets: Dict = {}
    task_ids = []
    # We'll keep this simple — one project_code per request
    #create_project_gcs_structure(client_id, project_code)

    datasets[project_code] = {
        "name": project_name.replace("_", " "),
        "client_id": client_id,
        "project_code": project_code,
        "assigned_by": assigned_by,
        "assigned_to": assigned_to,
        "datasets": [],
        "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),

    }

    for file in files:
        try:
            content = await file.read()  # bytes
            task_id = file.filename        
            processing_errors = {}

            # result = await handle_upload(
            #     content, 
            #     file.filename, 
            #     project_name,
            #     assigned_to,
            #     assigned_by,
            #     client_id,
            #     project_code,
            #     processing_errors or {}
            # )

            #Schedule background task (non-blocking)
            background_tasks.add_task(
                run_upload_task_background,
                task_id=task_id,
                file_content=content,
                filename=file.filename,
                project_name=project_name,
                assigned_to=assigned_to,
                assigned_by=assigned_by,
                client_id=client_id,
                project_code=project_code,
                processing_errors={}
            )

            task_ids.append(task_id) 

            # Add metadata for the JSON dump
            datasets[project_code]["datasets"].append({
                "dataset_id": project_code,           # ← maybe use uuid per file?
                "project_name": project_name.replace("_", " "),
                "project_code": project_code,
                "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                "status": "Pending",
                "client_id": client_id,
                "table_name": project_code,
                "filename": file.filename,
                "assigned_to": assigned_to,
                "assigned_by": assigned_by,
                "dataset_schema": "dataset_schema",   # ← placeholder?
                "meta_info": {},
                "created_at": datetime.utcnow().isoformat()
            })

        except Exception as e:
            print(f"Error reading file {file.filename}: {e}")
            # decide: continue or return early?

    # Optional: dump to JSON file (not recommended in production)
    # json_file = f"TEMP_DUMP_{project_code}_{client_id}.json"
    # try:
    #     with open(json_file, "w", encoding="utf-8") as f:
    #         json.dump(datasets, f, indent=2, default=str)
    # except Exception as e:
    #     print(f"Failed to write JSON dump: {e}")

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Accepted Uploads — processing {len(files)} file(s) in background ",
            "project_code": project_code,
            "client_id": client_id,
            "task_ids": task_ids,        
            "file_count": len(files),
        }
    )

@router.get("/datasets")
def list_datasets(client_id: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    """Return a list of all uploaded datasets, optionally filtered by client_id."""
    try:

        q = db.query(Dataset)
        if client_id:
            q = q.filter(Dataset.client_id == client_id, Dataset.is_deleted == False)

        datasets = {}
        project_codes = []
        for qs in q.all():
            datasets[qs.project_code] = {"datasets": []  } 

        for ds in q.all():
            #create_project_gcs_structure(ds.client_id, ds.project_code)

            datasets[qs.project_code] = {"datasets": []  } 
            dataset_schema = ds.schema
            try:
                dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
            except Exception:
                dataset_schema = ds.schema

            project_codes.append(ds.project_code)    
            datasets_record = datasets[ds.project_code]
            datasets[ds.project_code]["datasets"].append({
                "dataset_id": ds.dataset_id,
                "project_name": ds.project_name.replace("_"," "),
                "project_code": ds.project_code,
                "due_date": ds.due_date,
                "status": ds.status,
                "client_id": ds.client_id,
                "table_name": ds.table_name,
                "filename": ds.filename,
                "assigned_to": ds.assigned_to,
                "assigned_by": ds.assigned_by,
                "dataset_schema": dataset_schema, 
                "meta_info": ds.meta,              
                "created_at": ds.created_at
            })

            datasets[ds.project_code]["name"] = ds.project_name.replace("_"," ")
            datasets[ds.project_code]["client_id"] = ds.client_id
            datasets[ds.project_code]["project_code"] = ds.project_code
            datasets[ds.project_code]["due_date"] = ds.due_date
            datasets[ds.project_code]["assigned_by"] = ds.assigned_by
            datasets[ds.project_code]["assigned_to"] = ds.assigned_to

        project_meta = db.query(DatasetMeta)
        if project_meta:
            for project_code in project_codes:
                dataset_info = project_meta.filter(DatasetMeta.project_code == project_code).first()
                datasets[project_code]["dataset_info"] = dataset_info


        return {"status": True, "data": datasets}

    except Exception as e:        
        return {"status": False, "message": f"Error: Could not retreive datasets => Error details: {str(e)}"}

    finally:
        db.close()


@router.get("/datasets/{dataset_id}/schema")
def get_schema(dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch dataset schema for a given dataset ID."""
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        dataset_schema = ds.schema
        try:
            dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
        except Exception:
            dataset_schema = ds.schema

        return {"dataset_id": ds.dataset_id, "dataset_schema": dataset_schema}
    finally:
        db.close()


@router.get("/datasets/{project_code}")
def get_project(
    project_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch dataset schema for a given dataset ID."""
    try:
        q = db.query(Dataset)
        if project_code:
            q = q.filter(Dataset.project_code == project_code)

        datasets = {}
        for ds in q.all():
            create_project_gcs_structure(ds.client_id, ds.project_code)
            datasets[ds.project_code] = datasets.get(ds.project_code , {"datasets": []  } )
            dataset_schema = ds.schema
            
            try:
                dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
            except Exception:
                dataset_schema = ds.schema

            datasets_record = datasets[ds.project_code]

            datasets[ds.project_code]["datasets"].append({
                "dataset_id": ds.dataset_id,
                "project_name": ds.project_name.replace("_"," "),
                "project_code": ds.project_code,
                "due_date": ds.due_date,
                "status": ds.status,
                "client_id": ds.client_id,
                "table_name": ds.table_name,
                "filename": ds.filename,
                "assigned_to": ds.assigned_to,
                "assigned_by": ds.assigned_by,
                "dataset_schema": dataset_schema, 
                "meta_info": ds.meta,              
                "created_at": ds.created_at
            })

            datasets[ds.project_code]["name"] = ds.project_name.replace("_"," ")
            datasets[ds.project_code]["client_id"] = ds.client_id
            datasets[ds.project_code]["project_code"] = ds.project_code
            datasets[ds.project_code]["due_date"] = ds.due_date
            datasets[ds.project_code]["assigned_by"] = ds.assigned_by
            datasets[ds.project_code]["assigned_to"] = ds.assigned_to

        return {"status": True, "data": datasets}

    except Exception as e:        
        return {"status": False, "message": f"Error: Could not retreive datasets => Error details: {str(e)}"}

    finally:
        db.close()


# ───────────────────────────────────────────────────────────────────────────
# Endpoint: Soft Delete (Move to Trash)
# ───────────────────────────────────────────────────────────────────────────

@router.delete("/api/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    request: SoftDeleteRequest = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft delete a dataset - moves it to trash instead of permanent deletion
    
    The dataset will be:
    - Marked as deleted in the metadata
    - Table renamed with "trash_" prefix
    - Automatically permanently deleted after 30 days (configurable)
    
    Can be restored using POST /api/datasets/{dataset_id}/restore
    """
    # Find the dataset first
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Check access - user must own the dataset or be admin
    if dataset.client_id != current_user.get("client_id") and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Access denied - you can only delete your own datasets")
    
    # Perform soft delete
    result = soft_delete_dataset(
        db=db,
        dataset_id=dataset_id,
        user_id=current_user.get("sub"),
        reason=request.reason if request else None,
        permanent_delete_days=request.permanent_delete_days if request else 30
    )
    
    return result

# ───────────────────────────────────────────────────────────────────────────
# Endpoint: Restore from Trash
# ───────────────────────────────────────────────────────────────────────────

@router.post("/api/datasets/{dataset_id}/restore")
async def restore_dataset_endpoint(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Restore a soft-deleted dataset from trash
    
    This will:
    - Restore the dataset metadata
    - Rename the table back to its original name
    - Make the data accessible again
    """
    # Find the deleted dataset
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == True
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in trash")
    
    # Check access
    if dataset.client_id != current_user.get("client_id") and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Restore
    result = restore_dataset(
        db=db,
        dataset_id=dataset_id,
        user_id=current_user.get("sub")
    )
    
    return result

# ───────────────────────────────────────────────────────────────────────────
# Endpoint: List Trash
# ───────────────────────────────────────────────────────────────────────────

@router.get("/api/datasets/trash/list")
async def list_trash(
    client_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all datasets in trash (soft deleted)
    
    Returns datasets that:
    - Were deleted by the current user, OR
    - Belong to the current user's client_id, OR  
    - User is admin
    
    Includes days_until_permanent_delete for each item.
    """
    # Filter by current user's access
    if not current_user.get("is_admin"):
        if client_id and client_id != current_user.get("client_id"):
            raise HTTPException(status_code=403, detail="Access denied")
        client_id = current_user.get("client_id")
    
    result = list_trashed_datasets(
        db=db,
        client_id=client_id,
        limit=limit,
        offset=offset
    )
    
    return result

# ───────────────────────────────────────────────────────────────────────────
# Endpoint: Permanent Delete (Use with caution!)
# ───────────────────────────────────────────────────────────────────────────

@router.delete("/api/datasets/{dataset_id}/permanent")
async def permanent_delete_dataset_endpoint(
    dataset_id: str,
    confirm: bool = Query(False, description="Must be true to confirm permanent deletion"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a dataset from trash
    
    ⚠️ WARNING: This action CANNOT be undone!
    
    The dataset must already be in trash (soft deleted).
    Only admins or the original owner can permanently delete.
    """
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Must set confirm=true to permanently delete. This action cannot be undone!"
        )
    
    # Find the deleted dataset
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == True
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in trash")
    
    # Check access - only owner or admin
    if dataset.client_id != current_user.get("client_id") and not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Perform permanent deletion
    result = permanently_delete_dataset(
        db=db,
        dataset_id=dataset_id,
        user_id=current_user.get("sub")
    )
    
    return result


# ───────────────────────────────────────────────────────────────────────────
# Endpoint: Empty Trash (Admin only)
# ───────────────────────────────────────────────────────────────────────────

@router.delete("/api/datasets/trash/empty")
async def empty_trash(
    older_than_days: int = Query(365, ge=1, description="Delete items older than this many days"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Empty trash by permanently deleting all soft-deleted datasets older than X days
    
    Admin only endpoint.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
    
    # Find old deleted datasets
    old_datasets = db.query(Dataset).filter(
        Dataset.is_deleted == True,
        Dataset.deleted_at < cutoff_date
    ).all()
    
    deleted_count = 0
    errors = []
    
    for dataset in old_datasets:
        try:
            permanently_delete_dataset(
                db=db,
                dataset_id=dataset.dataset_id,
                user_id=current_user.get("sub")
            )
            deleted_count += 1
        except Exception as e:
            errors.append(f"Failed to delete {dataset.dataset_id}: {str(e)}")
    
    return {
        "success": True,
        "message": f"Emptied trash. {deleted_count} datasets permanently deleted.",
        "deleted_count": deleted_count,
        "errors": errors if errors else None
    }        