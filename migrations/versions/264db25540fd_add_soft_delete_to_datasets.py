"""add_soft_delete_to_datasets

Revision ID: 264db25540fd
Revises: 908ccfda5a93
Create Date: 2026-04-07 02:18:41.849793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '264db25540fd'
down_revision: Union[str, None] = '908ccfda5a93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """Add soft delete columns to datasets table"""
    
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
    
    # Create indexes for faster queries
    op.create_index('idx_datasets_is_deleted', 'datasets', ['is_deleted'])
    op.create_index('idx_datasets_deleted_at', 'datasets', ['deleted_at'])
    op.create_index('idx_datasets_deleted_by', 'datasets', ['deleted_by'])
    
    # Create DeletedDatasetLog table for audit trail
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
    
    # Create indexes for audit log
    op.create_index('idx_deleted_logs_dataset_id', 'deleted_dataset_logs', ['dataset_id'])
    op.create_index('idx_deleted_logs_client_id', 'deleted_dataset_logs', ['client_id'])
    op.create_index('idx_deleted_logs_deleted_at', 'deleted_dataset_logs', ['deleted_at'])
    
    print("✅ Soft delete migration complete!")

def downgrade():
    """Remove soft delete columns (use with caution!)"""
    
    # Drop audit log table
    op.drop_index('idx_deleted_logs_deleted_at', table_name='deleted_dataset_logs')
    op.drop_index('idx_deleted_logs_client_id', table_name='deleted_dataset_logs')
    op.drop_index('idx_deleted_logs_dataset_id', table_name='deleted_dataset_logs')
    op.drop_table('deleted_dataset_logs')
    
    # Drop indexes
    op.drop_index('idx_datasets_deleted_by', table_name='datasets')
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
    
    print("✅ Soft delete migration rolled back!")
