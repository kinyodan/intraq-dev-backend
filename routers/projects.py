from core.imports import *
from fastapi import APIRouter

router = APIRouter()

# ───────────────────────────────────────────────────────────────────────────
# PROJECT-LEVEL SOFT DELETE ENDPOINTS
# ───────────────────────────────────────────────────────────────────────────

@router.delete("/api/projects/{project_code}")
async def delete_project_endpoint(
    project_code: str,
    request: SoftDeleteRequest = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete an entire project and all its datasets"""
    result = soft_delete_project(
        db=db,
        project_code=project_code,
        user_id=current_user.get("sub"),
        reason=request.reason if request else None,
        permanent_delete_days=request.permanent_delete_days if request else 30
    )
    return result

@router.post("/api/projects/{project_code}/restore")
async def restore_project_endpoint(
    project_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore an entire project from trash"""
    result = restore_project(
        db=db,
        project_code=project_code,
        user_id=current_user.get("sub")
    )
    return result

@router.get("/api/projects/trash/list")
async def list_trashed_projects_endpoint(
    client_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all projects in trash (soft deleted)"""
    if not current_user.get("is_admin"):
        client_id = current_user.get("client_id")
    
    result = list_trashed_projects(
        db=db,
        client_id=client_id,
        limit=limit,
        offset=offset
    )
    return result

@router.delete("/api/projects/{project_code}/permanent")
async def permanent_delete_project_endpoint(
    project_code: str,
    confirm: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently delete a project from trash"""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true. This action cannot be undone!"
        )
    
    result = permanently_delete_project(
        db=db,
        project_code=project_code,
        user_id=current_user.get("sub")
    )
    return result