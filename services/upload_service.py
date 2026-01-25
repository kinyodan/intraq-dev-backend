# services/upload_service.py

import os
import uuid
import json
from utils.file_utils import read_file_bytes
from db import engine, SessionLocal
from models import Dataset, DatasetMeta ,Base  # ← Fixed import
import pandas as pd
import shortuuid
from sqlalchemy import text

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def infer_schema(df: pd.DataFrame):
    cols = []
    for c in df.columns:
        cols.append({"name": str(c), "dtype": str(df[c].dtype)})
    return cols

def save_dataframe_as_table(df: pd.DataFrame, table_name: str):
    """Save DataFrame as a table in the database"""
    print(f"💾 Attempting to save DataFrame to table: {table_name}")
    print(f"   Shape: {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"   Columns: {list(df.columns)}")
    
    try:
        # Test connection first
        with engine.connect() as conn:
            print("✅ Database connection test passed")
        
        # Try to save
        df.to_sql(table_name, engine, index=False, if_exists='replace')
        print(f"✅ Successfully saved to table: {table_name}")
        
        # Verify
        with engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"✅ Verified: {count} rows in table")
            
    except Exception as e:
        print(f"❌ Error in save_dataframe_as_table: {e}")
        raise

def store_metadata(
    project_name: str ,
    project_code: str,
    client_id: str, 
    dataset_id: str,
    processing_errors,
    table_name: str, 
    filename: str, 
    schema,
    row_count, 
    assigned_to=None,
    assigned_by=None,
    meta=None):

    db = SessionLocal()
    try:

        ds = Dataset(
            client_id=client_id,
            project_name=project_name.lower().replace(" ", "_"),
            project_code=project_code,
            processing_errors=processing_errors,
            assigned_to= assigned_to if assigned_to else "Admin",
            assigned_by=assigned_by if assigned_by else "Admin",
            dataset_id=dataset_id,
            table_name=table_name,
            filename=filename,
            schema=schema,
            meta=json.dumps(meta) if meta else None)
        db.add(ds)
        db.commit()
        db.refresh(ds)

        # Update or create datasetmeta 
        project_meta = db.query(DatasetMeta)
        if project_meta:
            project_meta = project_meta.filter(DatasetMeta.project_code == project_code).first()

            if meta:
                if project_meta:
                    project_meta.project_total_rows = project_meta.project_total_rows + row_count
                    ds_meta = DatasetMeta(
                        project_total_rows=project_meta.project_total_rows,
                        project_total_errors= project_meta.project_total_errors)

                    db.add(ds_meta)
                    db.commit()
                    db.refresh(ds_meta)
                    print(ds_meta)

                else:    
                    ds_meta = DatasetMeta(
                        project_code = project_code,
                        project_total_rows=row_count,
                        project_total_errors= 0)

                    db.add(ds_meta)
                    db.commit()
                    db.refresh(ds_meta)
                    print(ds_meta)

        return ds

    finally:
        db.close()  # Or use SessionLocal.remove() if using scoped_session

def handle_upload(
    file_obj, 
    filename: str, 
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code=False,
    processing_errors={}):
    """
    file_obj: bytes
    Returns dataset metadata
    """
    print(f"📁 handle_upload called for: {filename}")
    
    try:
        content = file_obj
        df = read_file_bytes(filename, content)
        print(f"✅ DataFrame loaded: {df.shape}")
        
        if df.empty:
            print("⚠️  Warning: DataFrame is empty!")
            return {"error": "Empty dataframe", "filename": filename}
        
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]

        dataset_id = str(uuid.uuid4())
        table_name = f"client_{client_id}_data_{dataset_id.replace('-', '_')}"
        
        print(f"📝 Dataset ID: {dataset_id}")
        print(f"🗄️  Table name: {table_name}")

        # Save file locally
        path = os.path.join(UPLOAD_FOLDER, f"{dataset_id}_{filename}")
        with open(path, "wb") as f:
            f.write(content)
        print(f"💾 File saved locally: {path}")

        # Save data to DB
        print("💿 Saving to database...")
        save_dataframe_as_table(df, table_name)

        # Infer schema
        schema = infer_schema(df)

        # Save metadata
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
            row_count= len(df),
            meta={"rows": len(df)}
        )

        print(f"✅ handle_upload completed successfully")
        
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
            "schema": schema
        }
        
    except Exception as e:
        print(f"❌ Error in handle_upload: {e}")
        import traceback
        traceback.print_exc()
        raise