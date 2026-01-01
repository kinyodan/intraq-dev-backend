import os
import json
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from services.onboarding_service import process_onboarding
from services.upload_service import handle_upload
from services.visualization_service import aggregate_for_chart, fetch_table_preview
from fastapi.middleware.cors import CORSMiddleware
from db import SessionLocal, engine
from models import Base, Dataset, DatasetMeta
from schemas import DatasetCreateResponse, DatasetInfo
import shortuuid

# Ensure metadata DB tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Intraq - Dynamic Dataset Ingest & Visualization API")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://intraqapp.simokai.com",
        "https://intraq.simokai.com",
        "http://localhost:3000",      # For local development
        "http://localhost:3001",      # For local development
        "http://127.0.0.1:3000",      # For local development
        "https://intraq-ui.vercel.app",
        "https://intraq-dashboard.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.post("/upload_dataset", response_model=dict)
async def upload_dataset(
    project_name: str = Form(...),
    client_id: str = Form(...),
    project_code: str = Form(...),
    file: UploadFile = File(...),
    assigned_to: str = Form(...), 
    assigned_by: str = Form(...), 
    ):
    print(project_name)
    print(client_id)
    print(project_code)
    print(UploadFile)


    if project_code == "null":
        project_code = f"PRJ-{shortuuid.ShortUUID().random(length=8).upper()}"

    """Upload a dataset file (Excel, CSV, etc.) and register metadata."""
    content = await file.read()
    try:
        result = handle_upload(
            content, 
            file.filename, 
            project_name,
            assigned_to,
            assigned_by,
            client_id,
            project_code,
            {})
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/datasets")
def list_datasets(client_id: str = Query(None)):
    """Return a list of all uploaded datasets, optionally filtered by client_id."""
    db = SessionLocal()
    try:

        q = db.query(Dataset)
        if client_id:
            q = q.filter(Dataset.client_id == client_id)

        datasets = {}
        project_codes = []
        for qs in q.all():
            datasets[qs.project_code] = {"datasets": []  } 

        for ds in q.all():
            dataset_schema = ds.schema
            try:
                dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
            except Exception:
                dataset_schema = ds.schema

            project_codes.append(ds.project_code)    
            datasets_record = datasets[ds.project_code]
            print("START datasets_record-datasets_record-datasets_record")
            print(ds.filename)
            print("END datasets_record-datasets_record-datasets_record")

            datasets[ds.project_code]["datasets"].append({
                "dataset_id": ds.dataset_id,
                "project_name": ds.project_name.replace("_"," "),
                "project_code": ds.project_code,
                "due_date": ds.due_date,
                "status": ds.status,
                "client_id": ds.client_id,
                "table_name": ds.table_name,
                "filename": ds.filename,
                "assigned_to": ds.assigned_to,
                "assigned_by": ds.assigned_by,
                "dataset_schema": dataset_schema, 
                "meta_info": ds.meta,              
                "created_at": ds.created_at
            })

            datasets[ds.project_code]["name"] = ds.project_name.replace("_"," ")
            datasets[ds.project_code]["client_id"] = ds.client_id
            datasets[ds.project_code]["project_code"] = ds.project_code
            datasets[ds.project_code]["due_date"] = ds.due_date
            datasets[ds.project_code]["assigned_by"] = ds.assigned_by
            datasets[ds.project_code]["assigned_to"] = ds.assigned_to

        project_meta = db.query(DatasetMeta)
        if project_meta:
            for project_code in project_codes:
                dataset_info = project_meta.filter(DatasetMeta.project_code == project_code).first()
                datasets[project_code]["dataset_info"] = dataset_info


        return {"status": True, "data": datasets}

    except Exception as e:        
        return {"status": False, "message": f"Error: Could not retreive datasets => Error details: {str(e)}"}

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

@app.get("/datasets/{project_code}")
def get_project(project_code: str):
    """Fetch dataset schema for a given dataset ID."""
    db = SessionLocal()
    try:
        q = db.query(Dataset)
        if project_code:
            q = q.filter(Dataset.project_code == project_code)

        datasets = {}
        for qs in q.all():
            datasets[qs.project_code] = {"datasets": []  } 

        for ds in q.all():
            dataset_schema = ds.schema
            try:
                dataset_schema = json.loads(ds.schema) if isinstance(ds.schema, str) else ds.schema
            except Exception:
                dataset_schema = ds.schema

            datasets_record = datasets[ds.project_code]
            print("START  datasets_record-datasets_record-datasets_record")
            print(datasets_record)
            print(ds.filename)
            print("END datasets_record-datasets_record-datasets_record")

            datasets[ds.project_code]["datasets"].append({
                "dataset_id": ds.dataset_id,
                "project_name": ds.project_name.replace("_"," "),
                "project_code": ds.project_code,
                "due_date": ds.due_date,
                "status": ds.status,
                "client_id": ds.client_id,
                "table_name": ds.table_name,
                "filename": ds.filename,
                "assigned_to": ds.assigned_to,
                "assigned_by": ds.assigned_by,
                "dataset_schema": dataset_schema, 
                "meta_info": ds.meta,              
                "created_at": ds.created_at
            })

            datasets[ds.project_code]["name"] = ds.project_name.replace("_"," ")
            datasets[ds.project_code]["client_id"] = ds.client_id
            datasets[ds.project_code]["project_code"] = ds.project_code
            datasets[ds.project_code]["due_date"] = ds.due_date
            datasets[ds.project_code]["assigned_by"] = ds.assigned_by
            datasets[ds.project_code]["assigned_to"] = ds.assigned_to

        return {"status": True, "data": datasets}

    except Exception as e:        
        return {"status": False, "message": f"Error: Could not retreive datasets => Error details: {str(e)}"}

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
