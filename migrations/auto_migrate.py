"""
Auto-migration script that runs on startup.
Adds missing columns without needing Alembic CLI.
Run this as part of your app startup or as a one-time script.
"""

from sqlalchemy import create_engine, text, inspect, Column, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSON
import os
from dotenv import load_dotenv

load_dotenv()

def get_engine():
    """Get database engine with proper settings"""
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./intraq_meta.db")
    
    if DATABASE_URL.startswith("postgresql://"):
        return create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                'sslmode': 'require',
                'connect_timeout': 30,
            } if 'sslmode' not in DATABASE_URL else {'connect_timeout': 30}
        )
    else:
        return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)

def table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def run_auto_migration():
    """Run automatic migrations"""
    engine = get_engine()
    
    print("🔍 Checking for missing columns...")
    
    # Soft delete columns for datasets table
    soft_delete_columns = [
        ('is_deleted', 'BOOLEAN DEFAULT FALSE'),
        ('deleted_at', 'TIMESTAMP WITH TIME ZONE'),
        ('deleted_by', 'VARCHAR(255)'),
        ('delete_reason', 'TEXT'),
        ('restored_at', 'TIMESTAMP WITH TIME ZONE'),
        ('restored_by', 'VARCHAR(255)'),
        ('original_table_name', 'VARCHAR(255)'),
    ]
    
    with engine.connect() as conn:
        # Add soft delete columns to datasets
        for col_name, col_type in soft_delete_columns:
            if not column_exists(engine, 'datasets', col_name):
                print(f"  ➕ Adding column: datasets.{col_name}")
                conn.execute(text(f"ALTER TABLE datasets ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            else:
                print(f"  ✅ Column exists: datasets.{col_name}")
        
        # Create indexes for soft delete columns
        indexes = [
            ('idx_datasets_is_deleted', 'datasets', 'is_deleted'),
            ('idx_datasets_deleted_at', 'datasets', 'deleted_at'),
        ]
        
        for idx_name, table, column in indexes:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"))
            print(f"  ✅ Index ready: {idx_name}")
        
        # Create deleted_dataset_logs table if not exists
        if not table_exists(engine, 'deleted_dataset_logs'):
            print("  ➕ Creating table: deleted_dataset_logs")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS deleted_dataset_logs (
                    id SERIAL PRIMARY KEY,
                    dataset_id VARCHAR NOT NULL,
                    client_id VARCHAR NOT NULL,
                    project_name VARCHAR NOT NULL,
                    project_code VARCHAR,
                    table_name VARCHAR NOT NULL,
                    filename VARCHAR NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    deleted_by VARCHAR NOT NULL,
                    deleted_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    delete_reason TEXT,
                    permanent_delete_scheduled_at TIMESTAMP WITH TIME ZONE,
                    dataset_snapshot JSONB
                )
            """))
            
            # Create indexes for audit log
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deleted_logs_dataset_id ON deleted_dataset_logs(dataset_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deleted_logs_client_id ON deleted_dataset_logs(client_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_deleted_logs_deleted_at ON deleted_dataset_logs(deleted_at)"))
            print("  ✅ Audit log table created")
        else:
            print("  ✅ Table exists: deleted_dataset_logs")
        
        conn.commit()
    
    print("✅ Auto-migration complete!")
    return True

if __name__ == "__main__":
    run_auto_migration()
