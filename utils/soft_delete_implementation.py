"""
Soft Delete Functionality for Intraq

Add these changes to implement a "trash" system instead of hard deletes.
"""

# ============================================================================
# STEP 1: Update models.py - Add soft delete fields to Dataset model
# ============================================================================

"""
Add these imports at the top of models.py if not already present:
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, func, ForeignKey, Text

Add these fields to the Dataset class in models.py:

class Dataset(Base):
    __tablename__ = "datasets"

    # ... existing fields ...
    
    # ═══════════════════════════════════════════════════════════════════
    # SOFT DELETE FIELDS (NEW)
    # ═══════════════════════════════════════════════════════════════════
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String, nullable=True)  # User who deleted
    delete_reason = Column(Text, nullable=True)  # Optional reason for deletion
    
    # For restore functionality
    restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(String, nullable=True)
    
    # Original table backup (if you want to rename table instead of actually deleting)
    original_table_name = Column(String, nullable=True)
    
    # ═══════════════════════════════════════════════════════════════════


# Optional: Create a separate Trash/DeletedDataset model for audit trail
class DeletedDatasetLog(Base):
    """Audit log for all deletions - useful for compliance"""
    __tablename__ = "deleted_dataset_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String, nullable=False, index=True)
    client_id = Column(String, nullable=False, index=True)
    project_name = Column(String, nullable=False)
    project_code = Column(String, nullable=True)
    table_name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    row_count = Column(Integer, nullable=False)
    deleted_by = Column(String, nullable=False)
    deleted_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    delete_reason = Column(Text, nullable=True)
    permanent_delete_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Store snapshot of metadata at time of deletion
    dataset_snapshot = Column(JSON, nullable=True)
"""


# ============================================================================
# STEP 2: Add to main.py - Soft Delete Service/Functions
# ============================================================================

SOFT_DELETE_CODE = '''
# ═══════════════════════════════════════════════════════════════════════════
# SOFT DELETE SERVICE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS - Add these to main.py
# ═══════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel
from typing import Optional

class SoftDeleteRequest(BaseModel):
    reason: Optional[str] = None
    permanent_delete_days: int = 30


class RestoreRequest(BaseModel):
    pass  # Empty body, just confirmation


# ───────────────────────────────────────────────────────────────────────────
# Endpoint: Soft Delete (Move to Trash)
# ───────────────────────────────────────────────────────────────────────────

@app.delete("/api/datasets/{dataset_id}")
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

@app.post("/api/datasets/{dataset_id}/restore")
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

@app.get("/api/datasets/trash/list")
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

@app.delete("/api/datasets/{dataset_id}/permanent")
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

@app.delete("/api/datasets/trash/empty")
async def empty_trash(
    older_than_days: int = Query(30, ge=1, description="Delete items older than this many days"),
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
'''


# ============================================================================
# STEP 3: Migration Script (if you need to add columns to existing database)
# ============================================================================

MIGRATION_SCRIPT = '''
"""
Migration: Add soft delete columns to existing datasets table

Run this script to add the necessary columns to your existing database:

    python migrate_add_soft_delete.py
"""

from sqlalchemy import create_engine, text, Column, Boolean, DateTime, String, Text
from sqlalchemy.ext.declarative import declarative_base
import os

# Get your database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/dbname")

def migrate():
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'datasets' 
            AND column_name = 'is_deleted'
        """))
        
        if result.fetchone():
            print("Soft delete columns already exist!")
            return
        
        print("Adding soft delete columns...")
        
        # Add columns
        conn.execute(text("""
            ALTER TABLE datasets 
            ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
            ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN deleted_by VARCHAR(255),
            ADD COLUMN delete_reason TEXT,
            ADD COLUMN restored_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN restored_by VARCHAR(255),
            ADD COLUMN original_table_name VARCHAR(255)
        """))
        
        # Create index for faster queries
        conn.execute(text("""
            CREATE INDEX idx_datasets_is_deleted ON datasets(is_deleted)
        """))
        conn.execute(text("""
            CREATE INDEX idx_datasets_deleted_at ON datasets(deleted_at)
        """))
        
        conn.commit()
        print("✅ Migration complete!")

if __name__ == "__main__":
    migrate()
'''


# ============================================================================
# STEP 4: Updated Dataset Model Definition (copy-paste ready)
# ============================================================================

COMPLETE_DATASET_MODEL = '''
class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    client_id = Column(String, index=True, nullable=False)
    project_name = Column(String, nullable=False)
    project_code = Column(String, nullable=True)
    status = Column(String, nullable=False, default="in-progress")
    due_date = Column(String, nullable=False, default=lambda: (datetime.utcnow() + timedelta(days=30)).isoformat())    
    processing_errors = Column(JSON, nullable=False, default={})
    assigned_to = Column(String, nullable=False, default="")
    assigned_by = Column(String, nullable=False, default="")
    dataset_id = Column(String, nullable=False)  
    table_name = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    schema = Column(JSON, nullable=False) 
    meta = Column(JSON, nullable=True)     
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # ═══════════════════════════════════════════════════════════════════
    # SOFT DELETE FIELDS (NEW - Add these to your model)
    # ═══════════════════════════════════════════════════════════════════
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String, nullable=True)
    delete_reason = Column(Text, nullable=True)
    restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(String, nullable=True)
    original_table_name = Column(String, nullable=True)
    # ═══════════════════════════════════════════════════════════════════
'''


# Save the code to a file
with open('soft_delete_implementation.py', 'w') as f:
    f.write(SOFT_DELETE_CODE)
    f.write('\n\n')
    f.write('# ═══════════════════════════════════════════════════════════════════════════\n')
    f.write('# MIGRATION SCRIPT\n')
    f.write('# ═══════════════════════════════════════════════════════════════════════════\n\n')
    f.write(MIGRATION_SCRIPT)
    f.write('\n\n')
    f.write('# ═══════════════════════════════════════════════════════════════════════════\n')
    f.write('# COMPLETE DATASET MODEL\n')
    f.write('# ═══════════════════════════════════════════════════════════════════════════\n\n')
    f.write(COMPLETE_DATASET_MODEL)

print("✅ Soft delete implementation saved to: soft_delete_implementation.py")
print("\nNext steps:")
print("1. Run the migration script to add columns to your database")
print("2. Copy the SOFT_DELETE_CODE section into your main.py")
print("3. Update your Dataset model with the new soft delete fields")
print("4. Add the DeletedDatasetLog model if you want audit logging")
