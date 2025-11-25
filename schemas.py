# schemas.py
from pydantic import BaseModel
from typing import List, Optional, Any

class ColumnMeta(BaseModel):
    name: str
    dtype: str

class DatasetCreateResponse(BaseModel):
    dataset_id: str
    table_name: str
    filename: str

class DatasetInfo(BaseModel):
    dataset_id: str
    client_id: str
    table_name: str
    filename: str
    uploaded_at: str
    schema: List[ColumnMeta]
    meta: Optional[Any]
