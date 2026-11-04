from core.imports import *
from fastapi import APIRouter

router = APIRouter()

# ======================
# CLIENTS ENDPOINTS
# ======================

@router.get("/clients")
async def get_all_clients(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Get all clients"""
    try:
        clients = db.query(Client).filter(Client.is_deleted != True).all()
        return {
            "status": True,
            "data": [
                {
                    "id": c.id,
                    "client_id": c.client_id,
                    "phone_number": c.phone_number,
                    "onboarded": c.onboarded,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None
                }
                for c in clients
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching clients: {e}")

@router.get("/users")
async def get_all_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Get all users"""
    try:
        users = db.query(User).all()
        return {
            "status": True,
            "data": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "client_id": u.client_id,
                    "sub": u.sub,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "updated_at": u.updated_at.isoformat() if u.updated_at else None
                }
                for u in users
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching users: {e}")

@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Get single client by client_id"""
    try:
        client = db.query(Client).filter(Client.client_id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return {
            "status": True,
            "data": {
                "id": client.id,
                "client_id": client.client_id,
                "phone_number": client.phone_number,
                "onboarded": client.onboarded,
                "created_at": client.created_at.isoformat() if client.created_at else None,
                "updated_at": client.updated_at.isoformat() if client.updated_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching client: {e}")

@router.get("/projects")
async def get_projects(
    client_id: str = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    """Get projects for a client"""
    try:
        query = db.query(Dataset).filter(Dataset.is_deleted != True)
        if client_id:
            query = query.filter(Dataset.client_id == client_id)
        projects = query.all()
        return {
            "status": True,
            "data": {
                "data": [
                    {
                        "id": p.id,
                        "client_id": p.client_id,
                        "project_name": p.project_name,
                        "project_code": p.project_code,
                        "status": p.status,
                        "due_date": p.due_date,
                        "created_at": p.created_at.isoformat() if p.created_at else None
                    }
                    for p in projects
                ]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching projects: {e}")

