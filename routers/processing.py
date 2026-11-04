from core.imports import *
from fastapi import APIRouter

router = APIRouter()

class DataProcessingRequest(BaseModel):
    remote_file: str
    headless: bool

@router.post("/api/process_session_data")
async def processing_session_data(
    project_code: str = Form(...),
    norm: int = Form(...), 
    remote_file: HttpUrl = Form(...), 
    headless: bool = False, 
    current_user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db),
):
    """
    Process session data by calling an external automation microservice.
    """
    EXTERNAL_API_BASE_URL = os.getenv("EXTERNAL_API_BASE_URL", "https://intraq-automations-16520908241.europe-west1.run.app") 
    EXTERNAL_AUTOMATION_FILE_BASE_URL = os.getenv("EXTERNAL_AUTOMATION_FILE_BASE_URL", "https://storage.googleapis.com/intraq-automations/automations/") 
    EXTERNAL_API_TIMEOUT = 30.0
    external_api_url = f"{EXTERNAL_API_BASE_URL}/run"
     
    payload = {
        "norm": norm,
        "remote_file": str(remote_file),
        "headless": headless , 
        "automation_file": f"{project_code}_automation.py"
    }
     
    try:
        print(f"DEBUG: Calling automation service: {external_api_url}")
        print(f"DEBUG: Payload: {payload}")

        async with httpx.AsyncClient(timeout=EXTERNAL_API_TIMEOUT) as client:
          response = await client.post(
                external_api_url,
                params=payload
            )

        print(f"DEBUG: Response status: {response.status_code}")
        print(f"DEBUG: Response body: {response.text}")

        response.raise_for_status()   # Raise error for 4xx/5xx

        return response.json()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "Gateway Timeout", 
            "message": f"External API timeout", "project_code": project_code}
        )

    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "Service Unavailable", "message": "Cannot connect to external service", "project_code": project_code}
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "Bad Gateway", "message": str(e), "project_code": project_code}
        )
    except httpx.HTTPStatusError as exc:
            print(f"DEBUG: HTTP error {exc.response.status_code}: {exc.response.text}")
            raise HTTPException(
                status_code=exc.response.status_code, 
                detail=f"Automation service returned error: {exc.response.text}"
            )
    except Exception as e:
        print(f"DEBUG: Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if response.status_code >= 400:
        try:
            error_detail = response.json()
        except:
            error_detail = response.text
            raise HTTPException(
                status_code=response.status_code,
                detail={"error": "External API Error", "external_response": error_detail, "project_code": project_code}
            )
         
    try:
        external_response = response.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500, 
            detail={"error": "Invalid Response", "project_code": project_code}
        )
     
    return {
        "status": "success",
        "project_code": project_code,
        "external_api_response": external_response,
        "requested_params": params,
        "processed_at": datetime.utcnow().isoformat()
    }
        
@router.get("/storage/folders")
def list_bucket_contents(
    project_code: str = Form(...),
    client_id: str = Form(...),
    #current_user: dict = Depends(get_current_user)
):
    """
    Returns full folder tree from mounted GCS bucket.
    """

    return {
        "status": True,
        "message": "Project folders data",
        "contents": get_directory_tree(client_id, project_code)
    }
