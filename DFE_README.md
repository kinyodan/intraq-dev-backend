# DFE Automation Service Integration

This service integrates the DFE (Data Form Entry) automation scripts with the Intraq backend.

## Files Created

1. **`services/dfe_automation_service.py`** - Main service module
2. **`dfe_integration_example.py`** - Example endpoints for main.py
3. **`run_dfe_test.py`** - Standalone test script

## Quick Start

### Option 1: Using BackgroundTasks (Recommended)

Add to your `main.py`:

```python
# At the top with other imports
from services.dfe_automation_service import dfe_service, run_dfe_automation_background

# Add endpoint
@app.post("/api/dfe/run-automation")
async def run_dfe_automation(
    background_tasks: BackgroundTasks,
    client_id: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    # Validate access
    if not dfe_service.validate_client_access(current_user, client_id):
        raise HTTPException(403, "Access denied")
    
    # Queue background job
    job_id = f"dfe_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    background_tasks.add_task(
        run_dfe_automation_background,
        client_id=client_id,
        user_id=current_user.get("sub")
    )
    
    return {"job_id": job_id, "status": "queued"}
```

### Option 2: Using Celery

```python
from services.dfe_automation_service import dfe_service

@celery_app.task(bind=True, max_retries=3)
def run_dfe_task(self, client_id: str, user_id: str = None):
    try:
        return dfe_service.run_automation_for_client(client_id, user_id)
    except Exception as exc:
        self.retry(exc=exc, countdown=2 ** self.request.retries)

# In endpoint:
task = run_dfe_task.delay(client_id, current_user.get("sub"))
```

## API Endpoints

### Run Automation
```bash
POST /api/dfe/run-automation
Content-Type: application/x-www-form-urlencoded

client_id=YOUR_CLIENT_ID&input_file=/path/to/file.csv  # input_file is optional
```

### Check Job Status
```bash
GET /api/dfe/job-status/{job_id}
```

### List Active Jobs
```bash
GET /api/dfe/active-jobs?client_id=YOUR_CLIENT_ID  # client_id is optional
```

### Run Pipeline (Clean → Normalize → Split)
```bash
POST /api/dfe/process-pipeline
Content-Type: application/x-www-form-urlencoded

input_file=/path/to/file.csv&client_id=YOUR_CLIENT_ID&split_by=caw
```

## Client ID Validation

By default, the service validates that the user's `client_id` matches the requested client. 

To customize, edit `validate_client_access()` in `services/dfe_automation_service.py`:

```python
def validate_client_access(self, user: dict, client_id: str) -> bool:
    # Your custom logic here
    # Check if user is admin
    if user.get("is_admin"):
        return True
    # Or check permissions
    return user.get("client_id") == client_id
```

## What the Automation Does

1. **Clean**: Fixes names, phone numbers, IDs, sex, dates
2. **Normalize**: Calculates age, GPS coordinates, standardizes locations
3. **Split**: Splits files by CAW, constituency, or polling center
4. **Output**: Saves to `~/dev/dfe/normalized/`

## Directory Structure

```
~/dev/dfe/
├── normalized/          # Output files go here
├── automation/
│   ├── csv_cleaner_v2.py
│   ├── data_normalizer_v2.py
│   ├── csv_splitter_v2.py
│   └── pipeline_v2.py
└── progress/            # Job progress files

~/dev/dataentry/backend/
├── services/
│   └── dfe_automation_service.py
├── main.py              # Add endpoints here
└── dfe_integration_example.py  # Reference
```

## Testing

Run the test script:
```bash
cd ~/dev/dataentry/backend
python run_dfe_test.py --client-id YOUR_CLIENT_ID --file /path/to/file.csv
```

Or test directly:
```python
from services.dfe_automation_service import dfe_service

# Process a file
result = dfe_service.process_file_pipeline(
    input_file="/path/to/file.csv",
    split_by="caw"
)
print(result)
```

## Logging

Logs are written to:
- Console (via Python logging)
- `~/dev/dfe/dfe_service.log`

## Environment Variables

None required, but you can set:
```bash
DFE_NORMALIZED_FOLDER=/custom/path  # Override output directory
```
