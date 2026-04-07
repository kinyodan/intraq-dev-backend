# Soft Delete Implementation - Quick Reference

## What This Implements

A **trash system** where deleting a dataset:
1. ✅ Marks it as deleted (soft delete)
2. ✅ Renames the table to hide it from normal queries
3. ✅ Keeps all data intact (can be restored)
4. ✅ Automatically deletes after 30 days (configurable)
5. ✅ Requires confirmation for permanent deletion

---

## Files Created

| File | Purpose |
|------|---------|
| `soft_delete_implementation.py` | Complete implementation code |
| `SOFT_DELETE_README.md` | This quick reference guide |

---

## Quick Setup (3 Steps)

### Step 1: Add Fields to Dataset Model

Add these fields to `models.py` in the `Dataset` class:

```python
class Dataset(Base):
    __tablename__ = "datasets"
    
    # ... your existing fields ...
    
    # NEW: Soft delete fields
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String, nullable=True)
    delete_reason = Column(Text, nullable=True)
    restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(String, nullable=True)
    original_table_name = Column(String, nullable=True)
```

### Step 2: Add Endpoints to main.py

Add these functions to `main.py`:

```python
# Helper functions
def soft_delete_dataset(db, dataset_id, user_id, reason=None):
    # Marks dataset as deleted, renames table
    pass

def restore_dataset(db, dataset_id, user_id):
    # Restores dataset from trash
    pass

def list_trashed_datasets(db, client_id=None):
    # Lists datasets in trash
    pass

def permanently_delete_dataset(db, dataset_id, user_id):
    # Actually deletes data (use with caution!)
    pass

# API Endpoints
@app.delete("/api/datasets/{dataset_id}")              # Move to trash
@app.post("/api/datasets/{dataset_id}/restore")        # Restore from trash
@app.get("/api/datasets/trash/list")                   # List trash contents
@app.delete("/api/datasets/{dataset_id}/permanent")    # Permanent delete
@app.delete("/api/datasets/trash/empty")             # Empty trash (admin)
```

See `soft_delete_implementation.py` for the complete code.

### Step 3: Run Migration

```bash
# Option A: Use Alembic (if you have migrations set up)
alembic revision -m "add soft delete fields"
# Edit the migration file to add columns
alembic upgrade head

# Option B: Run the migration script
cd ~/dev/dataentry/backend
python -c "
from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'your-db-url-here')
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text('''
        ALTER TABLE datasets 
        ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(255),
        ADD COLUMN IF NOT EXISTS delete_reason TEXT,
        ADD COLUMN IF NOT EXISTS restored_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS restored_by VARCHAR(255),
        ADD COLUMN IF NOT EXISTS original_table_name VARCHAR(255);
        
        CREATE INDEX IF NOT EXISTS idx_datasets_is_deleted ON datasets(is_deleted);
        CREATE INDEX IF NOT EXISTS idx_datasets_deleted_at ON datasets(deleted_at);
    '''))
    conn.commit()
    print('Migration complete!')
"
```

---

## API Usage Examples

### Delete (Move to Trash)

```bash
DELETE /api/datasets/abc-123
Content-Type: application/json

{
  "reason": "Duplicate upload",
  "permanent_delete_days": 30
}
```

Response:
```json
{
  "success": true,
  "dataset_id": "abc-123",
  "status": "deleted",
  "message": "Dataset moved to trash. Will be permanently deleted after 30 days.",
  "deleted_at": "2025-04-07T10:30:00Z",
  "permanent_delete_scheduled_at": "2025-05-07T10:30:00Z"
}
```

### Restore from Trash

```bash
POST /api/datasets/abc-123/restore
```

Response:
```json
{
  "success": true,
  "dataset_id": "abc-123",
  "status": "restored",
  "message": "Dataset restored from trash successfully"
}
```

### List Trash

```bash
GET /api/datasets/trash/list?limit=50
```

Response:
```json
{
  "datasets": [
    {
      "dataset_id": "abc-123",
      "project_name": "Wajir Survey",
      "filename": "survey_data.csv",
      "deleted_at": "2025-04-07T10:30:00Z",
      "delete_reason": "Duplicate upload",
      "days_until_permanent_delete": 23
    }
  ],
  "total": 1
}
```

### Permanent Delete (Use with Caution!)

```bash
DELETE /api/datasets/abc-123/permanent?confirm=true
```

Response:
```json
{
  "success": true,
  "status": "permanently_deleted",
  "message": "Dataset permanently deleted. This action cannot be undone."
}
```

---

## Frontend Integration

### Delete Button Flow

```javascript
// Soft delete (move to trash)
async function deleteDataset(datasetId) {
  const reason = prompt("Why are you deleting this? (optional)");
  
  const response = await fetch(`/api/datasets/${datasetId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason })
  });
  
  if (response.ok) {
    alert("Dataset moved to trash. You can restore it from the trash page.");
  }
}

// Restore from trash
async function restoreDataset(datasetId) {
  const response = await fetch(`/api/datasets/${datasetId}/restore`, {
    method: 'POST'
  });
  
  if (response.ok) {
    alert("Dataset restored successfully!");
  }
}
```

### Trash Page UI

```javascript
// List trash contents
async function loadTrash() {
  const response = await fetch('/api/datasets/trash/list');
  const data = await response.json();
  
  return data.datasets.map(item => ({
    ...item,
    daysLeft: item.days_until_permanent_delete,
    canRestore: true,
    canDeleteForever: true
  }));
}
```

---

## Security Features

| Feature | Description |
|---------|-------------|
| ✅ User Isolation | Users can only see/delete their own datasets |
| ✅ Admin Override | Admins can see/delete all datasets |
| ✅ Access Control | Users can't restore datasets they don't own |
| ✅ Audit Trail | Who deleted, when, and why is tracked |
| ✅ Confirmation Required | Permanent delete requires `confirm=true` |
| ✅ Grace Period | 30 days before automatic permanent deletion |

---

## Database Changes

### New Columns in `datasets` table:

| Column | Type | Description |
|--------|------|-------------|
| `is_deleted` | BOOLEAN | True if in trash |
| `deleted_at` | TIMESTAMP | When moved to trash |
| `deleted_by` | VARCHAR | Who deleted it |
| `delete_reason` | TEXT | Why it was deleted |
| `restored_at` | TIMESTAMP | When restored (if applicable) |
| `restored_by` | VARCHAR | Who restored it |
| `original_table_name` | VARCHAR | Original table name before rename |

### What Happens to Tables:

**Before Delete:**
- Table: `client_abc_data_xyz123`
- Status: Active, queryable

**After Soft Delete:**
- Table renamed: `trash_client_abc_data_xyz123_1712480000`
- `is_deleted` = true
- Hidden from normal queries

**After Restore:**
- Table renamed back: `client_abc_data_xyz123`
- `is_deleted` = false
- Queryable again

**After Permanent Delete:**
- Table dropped completely
- Row removed from `datasets` table
- Data gone forever

---

## Common Patterns

### Update Existing Queries to Exclude Deleted

```python
# Before (shows all including deleted)
datasets = db.query(Dataset).filter(Dataset.client_id == client_id).all()

# After (excludes deleted)
datasets = db.query(Dataset).filter(
    Dataset.client_id == client_id,
    Dataset.is_deleted == False  # Add this
).all()
```

### Show "Recently Deleted" Toast

```javascript
// After login or on dashboard
fetch('/api/datasets/trash/list?limit=5')
  .then(r => r.json())
  .then(data => {
    if (data.total > 0) {
      showToast(`You have ${data.total} datasets in trash. <a href="/trash">View</a>`);
    }
  });
```

---

## Questions?

See `soft_delete_implementation.py` for the complete code including:
- Full function implementations
- Pydantic request/response models
- Complete endpoint definitions
- Migration script
- Audit logging (DeletedDatasetLog model)
