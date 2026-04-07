# Soft Delete Implementation with Alembic (Elmbi)

## Migration Instructions

### Step 1: Create the Migration File

```bash
cd ~/dev/dataentry/backend

# Create a new Alembic migration
alembic revision -m "add_soft_delete_to_datasets"
```

This creates a file in `alembic/versions/` like:
- `alembic/versions/20250407_add_soft_delete_to_datasets.py`

### Step 2: Copy Migration Content

Open the newly created file and replace its contents with:

```python
"""add_soft_delete_to_datasets

Revision ID: abc123xyz456  # This will be auto-generated
Revises: previous_revision_id_here
Create Date: 2025-04-07 02:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'abc123xyz456'  # Will be auto-generated
down_revision = 'previous_revision_here'  # Your actual previous migration ID
branch_labels = None
depends_on = None


def upgrade():
    # Add soft delete columns
    op.add_column('datasets', sa.Column('is_deleted', sa.Boolean(), 
                                        server_default='false', 
                                        nullable=False))
    op.add_column('datasets', sa.Column('deleted_at', sa.DateTime(timezone=True), 
                                        nullable=True))
    op.add_column('datasets', sa.Column('deleted_by', sa.String(length=255), 
                                        nullable=True))
    op.add_column('datasets', sa.Column('delete_reason', sa.Text(), 
                                        nullable=True))
    op.add_column('datasets', sa.Column('restored_at', sa.DateTime(timezone=True), 
                                        nullable=True))
    op.add_column('datasets', sa.Column('restored_by', sa.String(length=255), 
                                        nullable=True))
    op.add_column('datasets', sa.Column('original_table_name', sa.String(length=255), 
                                        nullable=True))
    
    # Create indexes
    op.create_index('idx_datasets_is_deleted', 'datasets', ['is_deleted'])
    op.create_index('idx_datasets_deleted_at', 'datasets', ['deleted_at'])
    
    # Create audit log table
    op.create_table('deleted_dataset_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dataset_id', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('project_name', sa.String(), nullable=False),
        sa.Column('project_code', sa.String(), nullable=True),
        sa.Column('table_name', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('deleted_by', sa.String(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('delete_reason', sa.Text(), nullable=True),
        sa.Column('permanent_delete_scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dataset_snapshot', postgresql.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create audit log indexes
    op.create_index('idx_deleted_logs_dataset_id', 'deleted_dataset_logs', ['dataset_id'])
    op.create_index('idx_deleted_logs_client_id', 'deleted_dataset_logs', ['client_id'])


def downgrade():
    # Drop audit log table
    op.drop_index('idx_deleted_logs_client_id', table_name='deleted_dataset_logs')
    op.drop_index('idx_deleted_logs_dataset_id', table_name='deleted_dataset_logs')
    op.drop_table('deleted_dataset_logs')
    
    # Drop indexes
    op.drop_index('idx_datasets_deleted_at', table_name='datasets')
    op.drop_index('idx_datasets_is_deleted', table_name='datasets')
    
    # Drop columns
    op.drop_column('datasets', 'original_table_name')
    op.drop_column('datasets', 'restored_by')
    op.drop_column('datasets', 'restored_at')
    op.drop_column('datasets', 'delete_reason')
    op.drop_column('datasets', 'deleted_by')
    op.drop_column('datasets', 'deleted_at')
    op.drop_column('datasets', 'is_deleted')
```

**Or simply copy the file I created:**
```bash
cp ~/dev/dataentry/backend/alembic_migration_soft_delete.py \
   ~/dev/dataentry/backend/alembic/versions/$(date +%Y%m%d)_add_soft_delete.py
```

Then update the `revision` and `down_revision` IDs in the file.

### Step 3: Update models.py

Add these imports at the top:
```python
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, func, ForeignKey, Text
```

Add to `Dataset` class:
```python
# Soft delete fields
is_deleted = Column(Boolean, default=False, nullable=False, index=True)
deleted_at = Column(DateTime(timezone=True), nullable=True)
deleted_by = Column(String(255), nullable=True)
delete_reason = Column(Text, nullable=True)
restored_at = Column(DateTime(timezone=True), nullable=True)
restored_by = Column(String(255), nullable=True)
original_table_name = Column(String(255), nullable=True)
```

Add new `DeletedDatasetLog` class:
```python
class DeletedDatasetLog(Base):
    """Audit log for deleted datasets"""
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
    dataset_snapshot = Column(JSON, nullable=True)
```

### Step 4: Run Migration

```bash
cd ~/dev/dataentry/backend

# Apply the migration
alembic upgrade head

# Or to a specific revision
alembic upgrade add_soft_delete_to_datasets

# Check status
alembic current

# View history
alembic history
```

### Step 5: Add Soft Delete Functions to main.py

Copy the entire content from `soft_delete_implementation.py` and paste it into `main.py`.

Key functions to add:
1. `soft_delete_dataset()` - Move to trash
2. `restore_dataset()` - Restore from trash  
3. `list_trashed_datasets()` - List trash
4. `permanently_delete_dataset()` - Permanent delete

And these endpoints:
1. `DELETE /api/datasets/{id}` - Soft delete
2. `POST /api/datasets/{id}/restore` - Restore
3. `GET /api/datasets/trash/list` - List trash
4. `DELETE /api/datasets/{id}/permanent` - Permanent delete
5. `DELETE /api/datasets/trash/empty` - Empty trash

### Step 6: Test

```bash
# Check if columns were added
psql $DATABASE_URL -c "\d datasets"

# Should show:
#  is_deleted          | boolean                     | not null default false
#  deleted_at          | timestamp with time zone    | 
#  deleted_by          | character varying(255)      | 
#  delete_reason       | text                        | 
#  restored_at         | timestamp with time zone    | 
#  restored_by         | character varying(255)      | 
#  original_table_name | character varying(255)      | 
```

---

## Quick Reference: Alembic Commands

```bash
# Create new migration
alembic revision -m "description"

# Apply all migrations
alembic upgrade head

# Apply specific migration
alembic upgrade revision_id

# Rollback one migration
alembic downgrade -1

# Rollback to specific migration
alembic downgrade revision_id

# View current migration
alembic current

# View migration history
alembic history

# View pending migrations
alembic history --indicate-current

# Auto-generate migration from models (be careful!)
alembic revision --autogenerate -m "auto migration"
```

---

## Complete Code Ready to Copy

The file `alembic_migration_soft_delete.py` contains the complete Alembic migration.
Just copy it to your `alembic/versions/` folder and run `alembic upgrade head`.
