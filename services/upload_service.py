# services/upload_service.py
import os, uuid, json
from utils.file_utils import read_file_bytes
from db import engine, SessionLocal
from models.models import Dataset, Base
import pandas as pd
from sqlalchemy import text

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def infer_schema(df: pd.DataFrame):
    cols = []
    for c in df.columns:
        cols.append({"name": str(c), "dtype": str(df[c].dtype)})
    return cols

def save_dataframe_as_table(df: pd.DataFrame, table_name: str):
    """
    Write DataFrame to the DB using pandas to_sql.
    This creates a table in the same DB as metadata. For production,
    consider using a separate analytics store (duckdb or direct Postgres schema).
    """
    # Using the SQLAlchemy engine from db.py
    df.to_sql(table_name, engine, index=False, if_exists='replace')

def store_metadata(client_id: str, dataset_id: str, table_name: str, filename: str, schema, meta=None):
    db = SessionLocal()
    try:
        ds = Dataset(
            client_id=client_id,
            dataset_id=dataset_id,
            table_name=table_name,
            filename=filename,
            schema=schema,
            meta=json.dumps(meta) if meta else None
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
        return ds
    finally:
        db.close()

def handle_upload(file_obj, filename: str, client_id: str):
    """
    file_obj: bytes
    returns dataset metadata
    """
    content = file_obj
    df = read_file_bytes(filename, content)
    # Basic cleanup: strip whitespace column names
    df.columns = [str(c).strip() for c in df.columns]

    dataset_id = str(uuid.uuid4())
    # table naming: safe and unique
    table_name = f"client_{client_id}_data_{dataset_id.replace('-', '_')}"
    # Option: sanitize table name further

    # Save raw file locally
    path = os.path.join(UPLOAD_FOLDER, f"{dataset_id}_{filename}")
    with open(path, "wb") as f:
        f.write(content)

    # Save dataframe into DB as table
    save_dataframe_as_table(df, table_name)

    # Schema
    schema = infer_schema(df)

    # Save metadata
    ds = store_metadata(client_id, dataset_id, table_name, filename, schema, meta={"rows": len(df)})

    return {
        "dataset_id": dataset_id,
        "table_name": table_name,
        "filename": filename,
        "rows": len(df),
        "schema": schema
    }
