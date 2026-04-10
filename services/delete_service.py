



from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime, timedelta
import time
from fastapi import HTTPException
from models import Dataset, DeletedDatasetLog


def soft_delete_dataset(
    db: Session,
    dataset_id: str,
    user_id: str,
    reason: Optional[str] = None,
    permanent_delete_days: int = 30
) -> Dict:
    """
    Soft delete a dataset - marks as deleted but keeps data
    
    Args:
        db: Database session
        dataset_id: UUID of dataset to delete
        user_id: ID of user performing deletion
        reason: Optional reason for deletion
        permanent_delete_days: Days until permanent deletion (default 30)
        
    Returns:
        Dict with deletion status
    """
    from sqlalchemy import text
    
    # Find the dataset
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == False
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found or already deleted")
    
    # Get row count before deletion
    try:
        row_count_result = db.execute(
            text(f'SELECT COUNT(*) FROM "{dataset.table_name}"')
        ).scalar()
        row_count = row_count_result if row_count_result else 0
    except Exception as e:
        row_count = 0
        print(f"Warning: Could not get row count: {e}")
    
    # Mark as deleted
    dataset.is_deleted = True
    dataset.deleted_at = datetime.utcnow()
    dataset.deleted_by = user_id
    dataset.delete_reason = reason
    dataset.status = "deleted"  # Update status too
    
    # Optionally rename the table to indicate it's in trash
    # This prevents accidental queries but keeps data intact
    new_table_name = f"trash_{dataset.table_name}_{int(time.time())}"
    dataset.original_table_name = dataset.table_name
    
    try:
        # Rename the table (keeps data but moves it out of the way)
        db.execute(text(f'ALTER TABLE "{dataset.table_name}" RENAME TO "{new_table_name}"'))
        dataset.table_name = new_table_name
        print(f"Renamed table to {new_table_name}")
    except Exception as e:
        print(f"Warning: Could not rename table: {e}")
        # Continue anyway - the is_deleted flag is the primary mechanism
    
    # Create audit log
    deleted_log = DeletedDatasetLog(
        dataset_id=dataset_id,
        client_id=dataset.client_id,
        project_name=dataset.project_name,
        project_code=dataset.project_code,
        table_name=dataset.table_name,
        filename=dataset.filename,
        row_count=row_count,
        deleted_by=user_id,
        delete_reason=reason,
        permanent_delete_scheduled_at=datetime.utcnow() + timedelta(days=permanent_delete_days),
        dataset_snapshot={
            "schema": dataset.schema,
            "meta": dataset.meta,
            "assigned_to": dataset.assigned_to,
            "assigned_by": dataset.assigned_by
        }
    )
    db.add(deleted_log)
    
    # Commit changes
    db.commit()
    db.refresh(dataset)
    
    return {
        "success": True,
        "dataset_id": dataset_id,
        "status": "deleted",
        "message": f"Dataset moved to trash. Will be permanently deleted after {permanent_delete_days} days.",
        "deleted_at": dataset.deleted_at.isoformat() if dataset.deleted_at else None,
        "permanent_delete_scheduled_at": deleted_log.permanent_delete_scheduled_at.isoformat() if deleted_log.permanent_delete_scheduled_at else None,
        "row_count": row_count
    }


def restore_dataset(
    db: Session,
    dataset_id: str,
    user_id: str
) -> Dict:
    """
    Restore a soft-deleted dataset from trash
    
    Args:
        db: Database session
        dataset_id: UUID of dataset to restore
        user_id: ID of user performing restore
        
    Returns:
        Dict with restore status
    """
    from sqlalchemy import text
    
    # Find the deleted dataset
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == True
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in trash")
    
    # Restore the table name if it was renamed
    if dataset.original_table_name:
        try:
            db.execute(text(f'ALTER TABLE "{dataset.table_name}" RENAME TO "{dataset.original_table_name}"'))
            dataset.table_name = dataset.original_table_name
            dataset.original_table_name = None
            print(f"Restored table name to {dataset.table_name}")
        except Exception as e:
            print(f"Warning: Could not restore table name: {e}")
    
    # Mark as not deleted
    dataset.is_deleted = False
    dataset.deleted_at = None
    dataset.deleted_by = None
    dataset.delete_reason = None
    dataset.restored_at = datetime.utcnow()
    dataset.restored_by = user_id
    dataset.status = "restored"
    
    db.commit()
    db.refresh(dataset)
    
    return {
        "success": True,
        "dataset_id": dataset_id,
        "status": "restored",
        "message": "Dataset restored from trash successfully",
        "restored_at": dataset.restored_at.isoformat() if dataset.restored_at else None,
        "table_name": dataset.table_name
    }


def list_trashed_datasets(
    db: Session,
    client_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict:
    """
    List datasets in trash (soft deleted)
    
    Args:
        db: Database session
        client_id: Filter by client_id
        user_id: Filter by who deleted
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        Dict with list of trashed datasets and pagination info
    """
    query = db.query(Dataset).filter(Dataset.is_deleted == True)
    
    if client_id:
        query = query.filter(Dataset.client_id == client_id)
    
    if user_id:
        query = query.filter(Dataset.deleted_by == user_id)
    
    # Order by deletion date (most recent first)
    query = query.order_by(Dataset.deleted_at.desc())
    
    total = query.count()
    datasets = query.offset(offset).limit(limit).all()
    
    return {
        "datasets": [
            {
                "dataset_id": ds.dataset_id,
                "project_name": ds.project_name,
                "project_code": ds.project_code,
                "client_id": ds.client_id,
                "filename": ds.filename,
                "table_name": ds.table_name,
                "row_count": ds.schema.get("row_count") if ds.schema else None,
                "deleted_at": ds.deleted_at.isoformat() if ds.deleted_at else None,
                "deleted_by": ds.deleted_by,
                "delete_reason": ds.delete_reason,
                "days_until_permanent_delete": max(0, 30 - (datetime.utcnow() - ds.deleted_at).days) if ds.deleted_at else None
            }
            for ds in datasets
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


def permanently_delete_dataset(
    db: Session,
    dataset_id: str,
    user_id: str
) -> Dict:
    """
    Permanently delete a dataset (use with caution!)
    
    This actually drops the table and removes all records.
    Only use this for datasets already in trash.
    
    Args:
        db: Database session
        dataset_id: UUID of dataset to permanently delete
        user_id: ID of user performing deletion
        
    Returns:
        Dict with deletion status
    """
    from sqlalchemy import text
    
    # Find the deleted dataset
    dataset = db.query(Dataset).filter(
        Dataset.dataset_id == dataset_id,
        Dataset.is_deleted == True
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in trash")
    
    table_name = dataset.table_name
    
    # Actually drop the table
    try:
        db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        print(f"Dropped table {table_name}")
    except Exception as e:
        print(f"Warning: Could not drop table: {e}")
    
    # Delete from Cloudinary (optional)
    try:
        import json
        meta = json.loads(dataset.meta) if dataset.meta else {}
        cloudinary_public_id = meta.get("cloudinary_public_id")
        if cloudinary_public_id:
            # You would need to implement cloudinary deletion here
            print(f"Would delete from Cloudinary: {cloudinary_public_id}")
    except Exception as e:
        print(f"Warning: Could not delete from Cloudinary: {e}")
    
    # Remove the dataset record
    db.delete(dataset)
    db.commit()
    
    return {
        "success": True,
        "dataset_id": dataset_id,
        "status": "permanently_deleted",
        "message": "Dataset permanently deleted. This action cannot be undone.",
        "deleted_at": datetime.utcnow().isoformat()
    }


# =============================================================================
# PROJECT-LEVEL SOFT DELETE FUNCTIONS
# =============================================================================

def soft_delete_project(
    db: Session,
    project_code: str,
    user_id: str,
    reason: Optional[str] = None,
    permanent_delete_days: int = 30
) -> Dict:
    """
    Soft delete an entire project - marks all datasets under project_code as deleted
    
    Args:
        db: Database session
        project_code: The project code to delete
        user_id: ID of user performing deletion
        reason: Optional reason for deletion
        permanent_delete_days: Days until permanent deletion (default 30)
        
    Returns:
        Dict with deletion status and list of deleted datasets
    """
    from sqlalchemy import text
    
    # Find all datasets under this project that are not already deleted
    datasets = db.query(Dataset).filter(
        Dataset.project_code == project_code,
        Dataset.is_deleted == False
    ).all()
    
    if not datasets:
        raise HTTPException(status_code=404, detail="No datasets found for this project or already deleted")
    
    deleted_datasets = []
    failed_datasets = []
    total_rows = 0
    
    for dataset in datasets:
        try:
            # Get row count before deletion
            try:
                row_count_result = db.execute(
                    text(f'SELECT COUNT(*) FROM "{dataset.table_name}"')
                ).scalar()
                row_count = row_count_result if row_count_result else 0
            except Exception as e:
                row_count = 0
                print(f"Warning: Could not get row count for {dataset.dataset_id}: {e}")
            
            # Mark as deleted
            dataset.is_deleted = True
            dataset.deleted_at = datetime.utcnow()
            dataset.deleted_by = user_id
            dataset.delete_reason = f"Project deleted: {reason}" if reason else "Project deleted"
            dataset.status = "deleted"
            
            # Rename table
            new_table_name = f"trash_{dataset.table_name}_{int(time.time())}"
            dataset.original_table_name = dataset.table_name
            
            try:
                db.execute(text(f'ALTER TABLE "{dataset.table_name}" RENAME TO "{new_table_name}"'))
                dataset.table_name = new_table_name
                print(f"Renamed table to {new_table_name}")
            except Exception as e:
                print(f"Warning: Could not rename table for {dataset.dataset_id}: {e}")
            
            # Create audit log
            deleted_log = DeletedDatasetLog(
                dataset_id=dataset.dataset_id,
                client_id=dataset.client_id,
                project_name=dataset.project_name,
                project_code=dataset.project_code,
                table_name=dataset.table_name,
                filename=dataset.filename,
                row_count=row_count,
                deleted_by=user_id,
                delete_reason=f"Project deleted: {reason}" if reason else "Project deleted",
                permanent_delete_scheduled_at=datetime.utcnow() + timedelta(days=permanent_delete_days),
                dataset_snapshot={
                    "schema": dataset.schema,
                    "meta": dataset.meta,
                    "assigned_to": dataset.assigned_to,
                    "assigned_by": dataset.assigned_by
                }
            )
            db.add(deleted_log)
            
            deleted_datasets.append({
                "dataset_id": dataset.dataset_id,
                "filename": dataset.filename,
                "row_count": row_count
            })
            total_rows += row_count
            
        except Exception as e:
            failed_datasets.append({
                "dataset_id": dataset.dataset_id,
                "error": str(e)
            })
    
    db.commit()
    
    return {
        "success": True,
        "project_code": project_code,
        "status": "deleted",
        "message": f"Project moved to trash. {len(deleted_datasets)} dataset(s) soft deleted. Will be permanently deleted after {permanent_delete_days} days.",
        "deleted_at": datetime.utcnow().isoformat(),
        "permanent_delete_scheduled_at": (datetime.utcnow() + timedelta(days=permanent_delete_days)).isoformat(),
        "datasets_deleted": deleted_datasets,
        "datasets_failed": failed_datasets if failed_datasets else None,
        "total_datasets": len(deleted_datasets),
        "total_rows": total_rows
    }


def restore_project(
    db: Session,
    project_code: str,
    user_id: str
) -> Dict:
    """
    Restore all soft-deleted datasets under a project_code from trash
    
    Args:
        db: Database session
        project_code: The project code to restore
        user_id: ID of user performing restore
        
    Returns:
        Dict with restore status and list of restored datasets
    """
    from sqlalchemy import text
    
    # Find all deleted datasets under this project
    datasets = db.query(Dataset).filter(
        Dataset.project_code == project_code,
        Dataset.is_deleted == True
    ).all()
    
    if not datasets:
        raise HTTPException(status_code=404, detail="No deleted datasets found for this project")
    
    restored_datasets = []
    failed_datasets = []
    
    for dataset in datasets:
        try:
            # Restore table name
            if dataset.original_table_name:
                try:
                    db.execute(text(f'ALTER TABLE "{dataset.table_name}" RENAME TO "{dataset.original_table_name}"'))
                    dataset.table_name = dataset.original_table_name
                    dataset.original_table_name = None
                    print(f"Restored table name to {dataset.table_name}")
                except Exception as e:
                    print(f"Warning: Could not restore table name for {dataset.dataset_id}: {e}")
            
            # Mark as not deleted
            dataset.is_deleted = False
            dataset.deleted_at = None
            dataset.deleted_by = None
            dataset.delete_reason = None
            dataset.restored_at = datetime.utcnow()
            dataset.restored_by = user_id
            dataset.status = "restored"
            
            restored_datasets.append({
                "dataset_id": dataset.dataset_id,
                "filename": dataset.filename,
                "table_name": dataset.table_name
            })
            
        except Exception as e:
            failed_datasets.append({
                "dataset_id": dataset.dataset_id,
                "error": str(e)
            })
    
    db.commit()
    
    return {
        "success": True,
        "project_code": project_code,
        "status": "restored",
        "message": f"Project restored from trash. {len(restored_datasets)} dataset(s) restored.",
        "restored_at": datetime.utcnow().isoformat(),
        "datasets_restored": restored_datasets,
        "datasets_failed": failed_datasets if failed_datasets else None,
        "total_datasets": len(restored_datasets)
    }


def list_trashed_projects(
    db: Session,
    client_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict:
    """
    List all projects that have soft-deleted datasets (projects in trash)
    
    Args:
        db: Database session
        client_id: Filter by client_id
        limit: Pagination limit
        offset: Pagination offset
        
    Returns:
        Dict with list of trashed projects and their deleted datasets
    """
    from sqlalchemy import func
    
    # Query for projects with deleted datasets
    query = db.query(
        Dataset.project_code,
        Dataset.project_name,
        Dataset.client_id,
        func.count(Dataset.id).label('dataset_count'),
        func.max(Dataset.deleted_at).label('last_deleted_at')
    ).filter(
        Dataset.is_deleted == True
    ).group_by(
        Dataset.project_code,
        Dataset.project_name,
        Dataset.client_id
    )
    
    if client_id:
        query = query.filter(Dataset.client_id == client_id)
    
    # Order by most recently deleted
    query = query.order_by(func.max(Dataset.deleted_at).desc())
    
    total = query.count()
    projects = query.offset(offset).limit(limit).all()
    
    # Get details for each project
    projects_list = []
    for p in projects:
        # Get all deleted datasets for this project
        deleted_datasets = db.query(Dataset).filter(
            Dataset.project_code == p.project_code,
            Dataset.is_deleted == True
        ).all()
        
        total_rows = sum(
            ds.schema.get("row_count", 0) if ds.schema else 0 
            for ds in deleted_datasets
        )
        
        projects_list.append({
            "project_code": p.project_code,
            "project_name": p.project_name.replace("_", " ") if p.project_name else None,
            "client_id": p.client_id,
            "deleted_datasets_count": p.dataset_count,
            "total_rows": total_rows,
            "last_deleted_at": p.last_deleted_at.isoformat() if p.last_deleted_at else None,
            "days_until_permanent_delete": max(0, 30 - (datetime.utcnow() - p.last_deleted_at).days) if p.last_deleted_at else None,
            "datasets": [
                {
                    "dataset_id": ds.dataset_id,
                    "filename": ds.filename,
                    "deleted_at": ds.deleted_at.isoformat() if ds.deleted_at else None
                }
                for ds in deleted_datasets
            ]
        })
    
    return {
        "projects": projects_list,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def permanently_delete_project(
    db: Session,
    project_code: str,
    user_id: str
) -> Dict:
    """
    Permanently delete all datasets under a project (use with caution!)
    
    This actually drops all tables and removes all records.
    Only use this for projects already in trash (soft deleted).
    
    Args:
        db: Database session
        project_code: The project code to permanently delete
        user_id: ID of user performing deletion
        
    Returns:
        Dict with deletion status
    """
    from sqlalchemy import text
    
    # Find all deleted datasets under this project
    datasets = db.query(Dataset).filter(
        Dataset.project_code == project_code,
        Dataset.is_deleted == True
    ).all()
    
    if not datasets:
        raise HTTPException(status_code=404, detail="No deleted datasets found for this project")
    
    deleted_datasets = []
    failed_datasets = []
    
    for dataset in datasets:
        table_name = dataset.table_name
        
        # Actually drop the table
        try:
            db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            print(f"Dropped table {table_name}")
        except Exception as e:
            print(f"Warning: Could not drop table {table_name}: {e}")
            failed_datasets.append({
                "dataset_id": dataset.dataset_id,
                "error": str(e)
            })
            continue
        
        # Delete from Cloudinary (optional)
        try:
            import json
            meta = json.loads(dataset.meta) if dataset.meta else {}
            cloudinary_public_id = meta.get("cloudinary_public_id")
            if cloudinary_public_id:
                print(f"Would delete from Cloudinary: {cloudinary_public_id}")
        except Exception as e:
            print(f"Warning: Could not delete from Cloudinary: {e}")
        
        # Remove the dataset record
        db.delete(dataset)
        deleted_datasets.append(dataset.dataset_id)
    
    db.commit()
    
    return {
        "success": True,
        "project_code": project_code,
        "status": "permanently_deleted",
        "message": f"Project permanently deleted. {len(deleted_datasets)} dataset(s) removed. This action cannot be undone.",
        "deleted_at": datetime.utcnow().isoformat(),
        "datasets_deleted": deleted_datasets,
        "datasets_failed": failed_datasets if failed_datasets else None
    }
