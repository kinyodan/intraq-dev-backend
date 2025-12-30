# schemas.py
from pydantic import BaseModel
from typing import List, Optional, Any

class ColumnMeta(BaseModel):
    name: str
    dtype: str

class DatasetCreateResponse(BaseModel):
    dataset_id: str
    project_name: str
    project_code: str
    table_name: str
    filename: str
    created_at: str
    updated_at: str
    processing_errors: Optional[Any]
    status: str 
    due_date: str 
    assigned_to: str 
    assigned_by: str
    client_id: str

class DatasetInfo(BaseModel):
    dataset_id: str
    project_name: str
    project_code: str
    processing_errors: Optional[Any]
    assigned_to: str 
    assigned_by: str
    client_id: str
    table_name: str
    filename: str
    uploaded_at: str
    schema: List[ColumnMeta]
    meta: Optional[Any]
    status: str 
    due_date: str 
    created_at: str
    updated_at: str

class DatasetMeta(BaseModel):
    project_code: str
    project_total_rows: int
    project_total_errors: int
    project_errors: Optional[Any]