from fastapi import FastAPI, Request, Header, Form, HTTPException, Depends, status ,BackgroundTasks, APIRouter, Query, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from routers import authentication
import httpx
import time
import asyncio
from typing import Dict, Set
from alembic import command
from alembic.config import Config
from pydantic import BaseModel, EmailStr, HttpUrl
from jose import jwt, JWTError, ExpiredSignatureError
from datetime import datetime, timedelta
from passlib.context import CryptContext
import secrets, time, urllib.parse, re, hashlib, base64
import shortuuid
import os
from typing import List, Dict, Optional
import resend
import asyncio
import logging
import json
import ast
from fastapi_pagination import paginate , add_pagination
from fastapi_pagination.utils import disable_installed_extensions_check
from app.router import appRouter

from services.onboarding_service import process_onboarding
from services.upload_service import handle_upload
from services.visualization_service import aggregate_for_chart, fetch_table_preview
from db import SessionLocal, engine, DATABASE_URL
from models import Base, UserSession, AuthCode, User, Dataset, DatasetMeta, Package
from redis_db import init_redis_db
from services.redis_service import save_email_to_redis, get_emails_sync, get_emails_by_ids, get_email, save_reply_email_to_redis
from services.resend_service import get_full_email
from services.email_service import EmailInboxService
from schemas import DatasetCreateResponse, DatasetInfo
from sqlalchemy.orm import Session
import uuid  # or your generate_client_id()
from celery import Celery
from datetime import datetime
from services.email_service import IntraqTemplates
from services.telegram_service import send_telegram_msg 
from services.delete_service import (
    soft_delete_dataset,
    restore_dataset,
    list_trashed_datasets,
    permanently_delete_dataset,
    soft_delete_project,      # NEW
    restore_project,          # NEW
    list_trashed_projects,    # NEW
    permanently_delete_project, # NEW
)
from services.cloudflare_service import (    
    create_user_r2_structure,
    create_project_r2_structure,
    get_directory_tree
)

# ============================================================
# APPLICATION ROUTERS
# ============================================================

from routers import authentication
from routers.router import appRouter