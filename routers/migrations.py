from core.imports import *
from fastapi import APIRouter

router = APIRouter()


@router.post("/admin/migrate")
async def run_migrations(background_tasks: BackgroundTasks):
    """Run Alembic migrations - call this after deployment"""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    return {"status": "migrations completed"}

# Or for startup (runs every time app starts):
# @app.on_event("startup")
# async def startup_event():
#     """Run migrations on GETstartup"""
#     alembic_cfg = Config("alembic.ini")
#     command.upgrade(alembic_cfg, "head")