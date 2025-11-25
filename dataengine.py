import os
import json
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from db.models import Base, engine
from services.onboarding_service import process_onboarding
from services.upload_service import handle_upload
from services.visualization_service import aggregate_for_chart, fetch_table_preview
from db import SessionLocal, engine
from models.models import Base, Dataset
from schemas import DatasetCreateResponse, DatasetInfo

# Ensure metadata DB tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Intraq - Dynamic Dataset Ingest & Visualization API")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


@app.get("/")
def root():
    return {"status": "running"}

@app.get("/webhook")
async def verify_webhook(mode: str, challenge: str, token: str):
    """Verification handshake with Meta"""
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    return JSONResponse(status_code=403, content={"error": "Invalid token"})

@app.post("/webhook")
async def receive_message(request: Request):
    """Receives messages from WhatsApp Cloud API"""
    data = await request.json()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                messages = change.get("value", {}).get("messages", [])
                for msg in messages:
                    phone = msg["from"]
                    text = msg.get("text", {}).get("body", "")
                    process_onboarding(phone, text)
    except Exception as e:
        print("Webhook error:", e)
    return {"status": "ok"}


@app.post("/upload_dataset/", response_model=dict)
async def upload_dataset(client_id: str = Form(...), file: UploadFile = File(...)):
    """Upload a dataset file (Excel, CSV, etc.) and register metadata."""
    content = await file.read()
    try:
        result = handle_upload(content, file.filename, client_id)
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/datasets/", response_model=list[DatasetInfo])
def list_datasets(client_id: str = Query(None)):
    """Return a list of all uploaded datasets, optionally filtered by client_id."""
    db = SessionLocal()
    try:
        q = db.query(Dataset)
        if client_id:
            q = q.filter(Dataset.client_id == client_id)

        datasets = []
        for ds in q.all():
            dataset_schema = ds.schema
            try:
                dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
            except Exception:
                dataset_schema = ds.schema

            datasets.append({
                "dataset_id": ds.dataset_id,
                "client_id": ds.client_id,
                "table_name": ds.table_name,
                "filename": ds.filename,
                "uploaded_at": ds.uploaded_at.isoformat(),
                "dataset_schema": dataset_schema,  # renamed field for Pydantic safety
                "meta_info": ds.meta,              # renamed for clarity
            })

        return datasets
    finally:
        db.close()


@app.get("/datasets/{dataset_id}/schema")
def get_schema(dataset_id: str):
    """Fetch dataset schema for a given dataset ID."""
    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        dataset_schema = ds.schema
        try:
            dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
        except Exception:
            dataset_schema = ds.schema

        return {"dataset_id": ds.dataset_id, "dataset_schema": dataset_schema}
    finally:
        db.close()


@app.get("/visualize/")
def visualize(
    dataset_id: str = Query(...),
    x_column: str = Query(...),
    y_column: str = Query(...),
    agg: str = Query("sum")
):
    """Perform a simple aggregation for visualization (e.g., bar chart data)."""
    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        result = aggregate_for_chart(ds.table_name, x_column, y_column, agg)
        return result
    finally:
        db.close()


@app.get("/preview/")
def preview(dataset_id: str = Query(...), limit: int = Query(100)):
    """Preview dataset contents (for dashboard table or quick inspection)."""
    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        df = fetch_table_preview(ds.table_name, limit)
        return {"columns": df.columns.tolist(), "rows": df.to_dict(orient="records")}
    finally:
        db.close()
