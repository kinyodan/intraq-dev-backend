from fastapi import FastAPI, Request, Form, HTTPException, Depends, BackgroundTasks, Query, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError
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
from services.onboarding_service import process_onboarding
from services.upload_service import handle_upload
from services.visualization_service import aggregate_for_chart, fetch_table_preview
from db import SessionLocal, engine, DATABASE_URL
from models import Base, UserSession, AuthCode, User, Dataset, DatasetMeta, Package
from schemas import DatasetCreateResponse, DatasetInfo
from sqlalchemy.orm import Session
import uuid  # or your generate_client_id()
from celery import Celery
from datetime import datetime

app = FastAPI(title="Intraq - Dynamic Dataset Ingest & Visualization API")
REDIS_URL = os.getenv("REDIS_URL","redis://localhost:6379/0")

celery_app = Celery(
    'tasks',
    broker=REDIS_URL,  # Message broker
    backend=REDIS_URL,  # Result backend
    broker_connection_retry_on_startup=True
)

# Optional: Configure Celery settings
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,
)

# Ensure metadata DB tables exist
Base.metadata.create_all(bind=engine)
bearer_scheme = HTTPBearer()

# ======================
# CONFIG
# ======================
JWT_SECRET = "replace-this-with-long-random-secret"
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE = 60 * 60 * 24              # 1 minutes
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24   # 1 day
ISSUER = "https://auth.nx.com"        # your auth server domain
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

CLIENTS = {
    "landing-app": {
        "redirect_uris": ["https://landing.nx.com/auth/callback"],
        "name": "Landing App",
        "pkce_required": True
    },
    "dashboard-app": {
        "redirect_uris": ["https://app1.nx.com/auth/callback"],
        "name": "Dashboard",
        "pkce_required": True
    },
}

# ======================
# IN-MEMORY STORES
# ======================
USERS = {}
AUTH_CODES = {}
SESSIONS = {}
REFRESH_TOKENS = {}

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY", "re_ERQvhkZw_HyaFrLm1Fir7xLvw9PpazyQr")

# Assume pwd_ctx is your password hasher (e.g., passlib)
from passlib.context import CryptContext
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # For local development
        "http://localhost:3001",      # For local development
        "http://127.0.0.1:3000",      # For local development
        "https://intraqapp.simokai.com",
        "https://intraq.simokai.com",
        "https://intraq-ui.vercel.app",
        "https://intraq-dashboard.vercel.app",
        "https://dashboard.intraq.simokai.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================
# EMAIL MODELS & SERVICE
# ======================
class EmailContact(BaseModel):
    email: EmailStr
    name: str
    company: Optional[str] = None
    requirements: Optional[Dict] = None

class EmailTemplate(BaseModel):
    subject: str
    html_content: str
    text_content: Optional[str] = None

class EmailResult(BaseModel):
    success: bool
    email: str
    message_id: Optional[str] = None
    error: Optional[str] = None

class BulkEmailRequest(BaseModel):
    contacts: List[EmailContact]
    template_type: str = "introduction"  # "introduction" or "follow_up"
    batch_size: int = 50

class EmailResponse(BaseModel):
    success: bool
    message: str
    results: List[dict]
    total_sent: int
    total_failed: int

class EmailService:
    def __init__(self, from_email: str, from_name: str = "Intraq"):
        self.from_email = from_email
        self.from_name = from_name
        self.default_from = f"{from_name} <{from_email}>"

    async def send_single_email(
        self, 
        to_contact: EmailContact, 
        template: EmailTemplate,
        reply_to: Optional[str] = None
    ) -> EmailResult:
        """Send a single email to one contact"""
        try:
            params = {
                "from": self.default_from,
                "to": [to_contact.email],
                "subject": template.subject,
                "html": self._personalize_template(template.html_content, to_contact),
                "text": self._personalize_template(template.text_content, to_contact) if template.text_content else None,
                "reply_to": reply_to
            }

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            response = resend.Emails.send(params)
            
            print(f"Email sent successfully to {to_contact.email}: {response['id']}")
            return EmailResult(
                success=True,
                email=to_contact.email,
                message_id=response['id']
            )
            
        except Exception as e:
            print(f"Failed to send email to {to_contact.email}: {str(e)}")
            return EmailResult(
                success=False,
                email=to_contact.email,
                error=str(e)
            )

    async def send_bulk_emails(
        self,
        contacts: List[EmailContact],
        template: EmailTemplate,
        batch_size: int = 50,
        delay_between_batches: float = 1.0
    ) -> List[EmailResult]:
        """Send emails to multiple contacts with rate limiting"""
        results = []
        
        for i in range(0, len(contacts), batch_size):
            batch = contacts[i:i + batch_size]
            batch_tasks = []
            
            for contact in batch:
                task = self.send_single_email(contact, template)
                batch_tasks.append(task)
            
            # Process current batch
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
            
            # Rate limiting between batches
            if i + batch_size < len(contacts):
                await asyncio.sleep(delay_between_batches)
                
            print(f"Processed batch {i//batch_size + 1}/{(len(contacts)-1)//batch_size + 1}")
        
        return results

    def _personalize_template(self, content: str, contact: EmailContact) -> str:
        """Personalize email template with contact information"""
        if not content:
            return content
            
        replacements = {
            "{{name}}": contact.name,
            "{{first_name}}": contact.name.split()[0] if contact.name else "there",
            "{{company}}": contact.company or "your company",
            "{{email}}": contact.email
        }
        
        personalized = content
        for placeholder, value in replacements.items():
            personalized = personalized.replace(placeholder, value)
            
        return personalized

# Email templates for Intraq
class IntraqTemplates:
    @staticmethod
    def get_introduction_template(requirements: Optional[Dict] = None) -> EmailTemplate:
        base_subject = "Transform Your Data Strategy with Intraq - Reliable Data Solutions for Africa"
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                .cta-button { background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0; }
                .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Intraq</h1>
                    <p>Reliable Data Solutions for Africa's Leading Organizations</p>
                </div>
                <div class="content">
                    <h2>Hello {{first_name}},</h2>
                    
                    <p>I hope this message finds you well. I'm reaching out from <strong>Intraq</strong>, where we specialize in providing enterprise-grade data solutions tailored for African markets.</p>
                    
                    <p>We understand that {{company}} faces unique data challenges, and we're here to help you:</p>
                    
                    <ul>
                        <li>📊 Implement robust data infrastructure and pipelines</li>
                        <li>🔍 Gain actionable insights from your data assets</li>
                        <li>🌍 Navigate Africa-specific data regulations and markets</li>
                        <li>🚀 Scale your data capabilities as you grow</li>
                    </ul>

                    <p>Our solutions have helped organizations across the continent transform their data strategy and drive measurable business outcomes.</p>
                    
                    <p>Would you be open to a brief 15-minute call next week to discuss how Intraq could support {{company}}'s data initiatives?</p>
                    
                    <div style="text-align: center;">
                        <a href="https://calendly.com/intraq-demo/introduction" class="cta-button">Schedule a Discovery Call</a>
                    </div>
                    
                    <p>Alternatively, you can reply to this email directly - I'd be happy to answer any questions you might have.</p>
                    
                    <p>Looking forward to the possibility of working together!</p>
                    
                    <p>Best regards,<br>
                    <strong>The Intraq Team</strong></p>
                </div>
                <div class="footer">
                    <p>Intraq - Reliable Data Solutions for Africa<br>
                    <a href="https://intraq.simokai.com">Visit our website</a> | <a href="mailto:contact@intraq.com">Contact us</a></p>
                    <p><small>If you'd prefer not to receive these emails, please <a href="#">unsubscribe here</a>.</small></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return EmailTemplate(
            subject=base_subject,
            html_content=html_content
        )

    @staticmethod
    def get_follow_up_template() -> EmailTemplate:
        return EmailTemplate(
            subject="Following up: Data Solutions for {{company}}",
            html_content="""
            <!DOCTYPE html>
            <html>
            <body>
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2>Hi {{first_name}},</h2>
                    
                    <p>I wanted to follow up on my previous email about how Intraq could help {{company}} with data solutions.</p>
                    
                    <p>I understand you're busy, but I truly believe we could add significant value to your data initiatives.</p>
                    
                    <p>Would any of these be helpful?</p>
                    <ul>
                        <li>A quick 10-minute chat about your current data challenges</li>
                        <li>Specific case studies relevant to your industry</li>
                        <li>Information about our implementation process</li>
                    </ul>
                    
                    <p>No pressure at all - just let me know what would be most useful!</p>
                    
                    <p>Best,<br>
                    The Intraq Team</p>
                </div>
            </body>
            </html>
            """
        )

# Initialize email service
email_service = EmailService(
    from_email=os.getenv("FROM_EMAIL", "onboarding@resend.dev"),
    from_name="Intraq"
)

# ======================
# EXISTING AUTH HELPERS
# ======================

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Optional: check expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(status_code=401, detail="Token expired")
        # You can return user data if needed
        return {"sub": username }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def generate_client_id():
    return f"CL{shortuuid.ShortUUID().random(length=8).upper()}"

def create_token_payload(user, extra=None, expires=ACCESS_TOKEN_EXPIRE):
    iat = int(time.time())
    exp = iat + expires
    payload = {"iss": ISSUER, "sub": user.sub, "iat": iat, "exp": exp}
    if extra: payload.update(extra)
    return payload

def create_jwt(payload, expires_in=ACCESS_TOKEN_EXPIRE):
    iat = int(time.time())
    exp = iat + expires_in
    data = {"iss": ISSUER, "iat": iat, "exp": exp, **payload}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)
class TokenRequest(BaseModel):
    grant_type: str
    code: str = None
    redirect_uri: str = None
    client_id: str = None
    code_verifier: str = None
    refresh_token: str = None

# ======================
# EXISTING AUTH ENDPOINTS
# ======================

@app.post("/token")
async def token(req: TokenRequest, db: Session = Depends(get_db)):

    if req.grant_type == "authorization_code":
        
        # Find authorization code  
        code_data = db.query(AuthCode).filter(
            (AuthCode.code == req.code)
        ).first()

        # code_data = AUTH_CODES.pop(req.code, None)
        # if not code_data or code_data["expires_at"] < time.time():
            # raise HTTPException(status_code=400, detail="Invalid or expired code")

        if code_data and code_data.code_challenge:
            if not req.code_verifier:
                raise HTTPException(status_code=400, detail="PKCE required")
            v = hashlib.sha256(req.code_verifier.encode()).digest()
            expected = base64.urlsafe_b64encode(v).rstrip(b"=").decode()
            if expected != code_data.code_challenge:
                raise HTTPException(status_code=400, detail="PKCE verification failed")

        if code_data and code_data.user_id:
            user = db.query(User).filter((User.id == code_data.user_id)).first()
            access = create_token_payload(user, extra={"scope": "openid"}, expires=ACCESS_TOKEN_EXPIRE)
            refresh = secrets.token_urlsafe(48)
            REFRESH_TOKENS[refresh] = {"user": user, "expires": time.time() + REFRESH_TOKEN_EXPIRE}
            user_data = {"username": user.username, "client_id": user.client_id}

            return {
                "access_token": jwt.encode(access, JWT_SECRET, algorithm=JWT_ALG),
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE,
                "refresh_token": refresh,
                "user": user_data
            }
        else:
            raise HTTPException(status_code=400, detail="Missing attribute user in request")  
       

    elif req.grant_type == "refresh_token":
        data = REFRESH_TOKENS.get(req.refresh_token)
        if not data or data["expires"] < time.time():
            raise HTTPException(status_code=400, detail="Invalid refresh token")
        user = data["user"]
        access = create_token_payload(user, extra={"scope": "openid"}, expires=ACCESS_TOKEN_EXPIRE)
        new_refresh = secrets.token_urlsafe(48)
        REFRESH_TOKENS[new_refresh] = {"user": user, "expires": time.time() + REFRESH_TOKEN_EXPIRE}
        del REFRESH_TOKENS[req.refresh_token]
        return {
            "access_token": jwt.encode(access, JWT_SECRET, algorithm=JWT_ALG),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE,
            "refresh_token": new_refresh
        }

    raise HTTPException(status_code=400, detail="Unsupported grant_type")  

@app.get("/session")
async def session(request: Request):
    """If a valid session cookie exists, issue a short-lived access token."""
    session_id = request.cookies.get("auth_session")
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="No active session")

    sess = SESSIONS[session_id]
    if sess["expires"] < time.time():
        del SESSIONS[session_id]
        raise HTTPException(status_code=401, detail="Session expired")

    user = sess["user"]
    access = create_token_payload(user, extra={"scope": "openid"}, expires=ACCESS_TOKEN_EXPIRE)
    token = jwt.encode(access, JWT_SECRET, algorithm=JWT_ALG)
    return {"access_token": token, "user": {"username": user["username"], "email": user["email"]}}

@app.post("/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check existing user
    existing_user = db.query(User).filter(
        (User.username == username) | (User.email == email.lower())
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    client_id = generate_client_id()  # Your function
    sub = f"user-{db.query(User).count() + 1}"  # Or use uuid.uuid4()

    new_user = User(
        username=username,
        email=email.lower(),
        password=pwd_ctx.hash(password),
        client_id=client_id,
        sub=sub
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "username": username,
        "email": email,
        "client_id": client_id
    }

@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(None),
    redirect_uri: str = Form(None),
    state: str = Form(None),
    code_challenge: str = Form(None),
    code_challenge_method: str = Form(None),
    db: Session = Depends(get_db)
):
    identifier = username.strip().lower()
    
    # Find user by username OR email
    user = db.query(User).filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()
    
    if not user or not pwd_ctx.verify(password, user.password):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Invalid credentials",
                "message": "Username or password is incorrect"
            }
        )

    # Generate session
    session_id = secrets.token_urlsafe(32)
    expires = time.time() + 3600  # 1 hour (adjust as needed)
    
    new_session = UserSession(
        session_id=session_id,
        user_id=user.id,
        expires_at=datetime.utcfromtimestamp(expires)
    )
    db.add(new_session)

    # Generate auth code for OAuth-like flow
    code = secrets.token_urlsafe(32)
    auth_expires = time.time() + 300  # 5 minutes
    
    new_auth_code = AuthCode(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=user.id,
        expires_at=datetime.utcfromtimestamp(auth_expires)
    )
    db.add(new_auth_code)
    
    db.commit()

    # Build query params for redirect
    q = {"code": code}
    if state:
        q["state"] = state

    # Build the redirect URL that frontend will use
    redirect_url = f"{redirect_uri}?{urllib.parse.urlencode(q)}" if redirect_uri else None

    # Prepare response data
    response_data = {
        "success": True,
        "message": "Authentication successful",
        "redirect_uri": redirect_url,  # The URL frontend should redirect to
        "auth_data": {
            "session_id": session_id,
            "access_token": "",  # if you generate JWT later, put here
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": "",
            "state": state
        },
        "cookie_config": {
            "name": "auth_session",
            "value": session_id,
            "options": {
                "httponly": True,
                "secure": True,
                "samesite": "none",
                "domain": ".nx.com",
                "path": "/",
                "max_age": 3600  # 1 hour
            }
        }
    }

    # Create JSON response
    resp = JSONResponse(
        content=response_data,
        status_code=200
    )

    # Set cookie on backend response
    resp.set_cookie(
        key="auth_session",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="none",
        domain=".nx.com",
        max_age=3600
    )
   
    print(f"Redirect URL for frontend: {redirect_url}")
    return resp

@app.get("/authorize")
async def authorize(request: Request, response_type: str, client_id: str, redirect_uri: str,
                    state: str = None, code_challenge: str = None, code_challenge_method: str = None):
    client = CLIENTS.get(client_id)
    if not client or redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="Invalid client or redirect_uri")

    session_id = request.cookies.get("auth_session")
    if session_id and session_id in SESSIONS:
        session = SESSIONS[session_id]
        if session["expires"] > time.time():
            # already logged in
            code = secrets.token_urlsafe(32)
            AUTH_CODES[code] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "user": session["user"],
                "expires_at": time.time() + 300
            }
            q = {"code": code}
            if state: q["state"] = state
            dest = redirect_uri + "?" + urllib.parse.urlencode(q)
            return RedirectResponse(dest)

    # no valid session → show login form
    html = f"""
    <html><body>
      <h2>Login to continue to {client_id}</h2>
      <form method="post" action="/login">
        <input type="hidden" name="client_id" value="{client_id}">
        <input type="hidden" name="redirect_uri" value="{redirect_uri}">
        <input type="hidden" name="state" value="{state or ''}">
        <input type="hidden" name="code_challenge" value="{code_challenge or ''}">
        <input type="hidden" name="code_challenge_method" value="{code_challenge_method or ''}">
        Username or Email: <input name="username"><br>
        Password: <input name="password" type="password"><br>
        <button>Login</button>
      </form>
    </body></html>
    """
    return HTMLResponse(html)

@app.post("/set_package")
async def set_client_package(
    client_id: str = Form(...),
    package_name: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        print(f"Current user: {current_user}")

        # Check if a package already exists for this client_id
        existing_package = db.query(Package).filter(Package.client_id == client_id).first()

        if existing_package:
            # Update existing package
            existing_package.previous_package  = existing_package.package_name 
            existing_package.package_name = package_name
            existing_package.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_package)
            return JSONResponse(
                status_code=200,
                content={
                    "message": f"Package updated to '{package_name}' for client {client_id}",
                    "package": {
                        "id": existing_package.id,
                        "client_id": existing_package.client_id,
                        "package_name": existing_package.package_name,
                        "previous_package": existing_package.previous_package,
                        "started_with": existing_package.started_with
                    }
                }
            )
        else:
            # Create new package
            new_package = Package(
                client_id=client_id,
                package_name=package_name,
                previous_package=package_name,
                started_with=package_name
            )
            db.add(new_package)
            db.commit()
            db.refresh(new_package)
            return JSONResponse(
                status_code=201,
                content={
                    "message": f"Package '{package_name}' set for client {client_id}",
                    "package": {
                        "id": new_package.id,
                        "client_id": new_package.client_id,
                        "package_name": new_package.package_name,
                        "previous_package": new_package.previous_package,
                        "started_with": new_package.started_with
                    }
                }
            )

    except Exception as e:
        db.rollback()  # rollback on error
        print(f"Error setting package: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Problem setting client package. Client ID might be missing or invalid: {str(e)}"
        )
            
class PackagesResponse(BaseModel):
    client_id: str
    package_name: str
    previous_package: str
    started_with: str
class PackageRequest(BaseModel):
    client_id: str

@app.get("/packages/{client_id}", response_model=PackagesResponse)
async def getPackages(
    client_id: str,
    db: Session = Depends(get_db)
):
    try:
        package = db.query(Package).filter(Package.client_id == client_id).first()
        if package:
            return JSONResponse(
                status_code=201,
                content={
                    "message": f"Package retreived successfully for client {client_id}",
                    "package": {
                        "id": package.id,
                        "client_id": package.client_id,
                        "package_name": package.package_name,
                        "previous_package": package.previous_package,
                        "started_with": package.started_with
                    }
                }
            )
        else:
            return JSONResponse(status_code=404, content="Package not found")    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Problem retreiving package Error: {e}") 


# ======================
# NEW EMAIL ENDPOINTS
# ======================
@app.post("/api/emails/send-bulk", response_model=EmailResponse)
async def send_bulk_emails(
    request: BulkEmailRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Send bulk emails to multiple contacts"""
    try:
        # Get appropriate template
        if request.template_type == "introduction":
            template = IntraqTemplates.get_introduction_template()
        elif request.template_type == "follow_up":
            template = IntraqTemplates.get_follow_up_template()
        else:
            raise HTTPException(status_code=400, detail="Invalid template type")

        # Send emails
        results = await email_service.send_bulk_emails(
            contacts=request.contacts,
            template=template,
            batch_size=request.batch_size
        )

        # Calculate stats
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        return EmailResponse(
            success=True,
            message=f"Email campaign completed. Sent: {len(successful)}, Failed: {len(failed)}",
            results=[r.dict() for r in results],
            total_sent=len(successful),
            total_failed=len(failed)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send emails: {str(e)}")

@app.post("/api/emails/send-test")
async def send_test_email():
    """Send a test email to verify configuration"""
    test_contact = EmailContact(
        email="kinyodaniel@outlook.com",
        name="Daniel Kinyo",
        company="Test Company"
    )
    
    template = IntraqTemplates.get_introduction_template()
    
    result = await email_service.send_single_email(test_contact, template)
    
    if result.success:
        return {"success": True, 
        "message": "Test email sent successfully", 
        "message_id": result.message_id}
    else:
        raise HTTPException(status_code=500, 
            detail=f"Failed to send test email: {result.error}")

@app.get("/api/emails/templates/{template_type}")
async def get_template_preview(template_type: str,   
    current_user: dict = Depends(get_current_user)
):
    """Preview email templates"""
    if template_type == "introduction":
        template = IntraqTemplates.get_introduction_template()
    elif template_type == "follow_up":
        template = IntraqTemplates.get_follow_up_template()
    else:
        raise HTTPException(status_code=400, detail="Invalid template type")
    
    return {
        "subject": template.subject,
        "html_content": template.html_content
    }

@app.get("/webhook")
async def verify_webhook(
    mode: str, 
    challenge: str,
    token: str,
    current_user: dict = Depends(get_current_user)
):
    """Verification handshake with Meta"""
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    return JSONResponse(status_code=403, content={"error": "Invalid token"})

@app.post("/webhook")
async def receive_message(request: Request,
    current_user: dict = Depends(get_current_user),
):
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

@celery_app.task(bind=True, max_retries=3)
def run_upload_task(
    self,
    file_content, 
    filename: str, 
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code=False,
    processing_errors={}
    ):
    
    print("=" * 50)
    print(f"🚀 CELERY TASK STARTED: {filename}")
    print(f"📦 File size: {len(file_content)} bytes")
    print(f"🏢 Project: {project_name}")
    print(f"👤 Client: {client_id}")
    print(f"🎯 Task ID: {self.request.id}")
    print("=" * 50)
    
    try:
        
        # Call your function
        result = handle_upload(
            file_content, 
            filename, 
            project_name,
            assigned_to,
            assigned_by,
            client_id,
            project_code,
            processing_errors or {}
        )
        
        print(f"✅ Task completed successfully!")
        print(f"📊 Result: {result}")
        print("=" * 50)
        
        return result
        
    except Exception as exc:
        print(f"❌ Task failed: {exc}")
        import traceback
        traceback.print_exc()
        
        # Retry with exponential backoff
        self.retry(exc=exc, countdown=2 ** self.request.retries)

# ────────────────────────────────────────────────
#   Background function – still def (not async def)
# ────────────────────────────────────────────────
def run_upload_task_background(
    task_id: str,                   # ← new: your own ID
    file_content: bytes,
    filename: str,
    project_name: str,
    assigned_to: str,
    assigned_by: str,
    client_id: str,
    project_code: str,
    processing_errors: Dict = None
):
    processing_errors = processing_errors or {}

    print("=" * 60)
    print(f"🚀 BACKGROUND TASK STARTED       | Task ID: {task_id}")
    print(f"   File: {filename:<30} | Size: {len(file_content):,} bytes")
    print(f"   Project: {project_name} ({project_code})")
    print(f"   Client: {client_id}  | Assigned: {assigned_to}")
    print("=" * 60)

    start_time = datetime.utcnow()

    try:
        # Call your real processing logic
        result = handle_upload(
            file_content=file_content,
            filename=filename,
            project_name=project_name,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            client_id=client_id,
            project_code=project_code,
            processing_errors=processing_errors
        )

        duration = (datetime.utcnow() - start_time).total_seconds()

        print(f"✅ TASK COMPLETED SUCCESSFULLY   | Task ID: {task_id}")
        print(f"   Duration: {duration:.2f} seconds")
        print(f"   Result: {result}")
        print("=" * 60)

        # Optional: update some status store
        # update_task_status(task_id, "success", result=result, duration=duration)

        return result  # ← return value is ignored by BackgroundTasks

    except Exception as exc:
        duration = (datetime.utcnow() - start_time).total_seconds()

        print(f"❌ TASK FAILED                    | Task ID: {task_id}")
        print(f"   Error: {exc}")
        print(f"   Duration: {duration:.2f} seconds")
        print("=" * 60)

        # Important: log somewhere persistent
        # log_error(task_id, filename, exc)
        # update_task_status(task_id, "failed", error=str(exc), duration=duration)

        raise   # ← re-raise if you want to see it in logs / sentry

# ────────────────────────────────────────────────
#               FIXED ENDPOINT
# ────────────────────────────────────────────────
@app.post("/upload_dataset", response_model=dict)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    project_name: str = Form(...),
    client_id: str = Form(...),
    project_code: str = Form(...),
    files: List[UploadFile] = File(...),
    assigned_to: str = Form(...),
    assigned_by: str = Form(...),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    if project_code == "null":
        project_code = f"PRJ-{shortuuid.ShortUUID().random(length=8).upper()}"

    datasets: Dict = {}
    # We'll keep this simple — one project_code per request

    datasets[project_code] = {
        "name": project_name.replace("_", " "),
        "client_id": client_id,
        "project_code": project_code,
        "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "assigned_by": assigned_by,
        "assigned_to": assigned_to,
        "datasets": []
    }

    for file in files:
        try:
            content = await file.read()  # bytes

            # Schedule background task (non-blocking)
            background_tasks.add_task(
                run_upload_task_background,
                file_content=content,
                filename=file.filename,
                project_name=project_name,
                assigned_to=assigned_to,
                assigned_by=assigned_by,
                client_id=client_id,
                project_code=project_code,
                processing_errors={}
            )

            # Add metadata for the JSON dump
            datasets[project_code]["datasets"].append({
                "dataset_id": project_code,           # ← maybe use uuid per file?
                "project_name": project_name.replace("_", " "),
                "project_code": project_code,
                "due_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                "status": "Pending",
                "client_id": client_id,
                "table_name": project_code,
                "filename": file.filename,
                "assigned_to": assigned_to,
                "assigned_by": assigned_by,
                "dataset_schema": "dataset_schema",   # ← placeholder?
                "meta_info": {},
                "created_at": datetime.utcnow().isoformat()
            })

        except Exception as e:
            print(f"Error reading file {file.filename}: {e}")
            # decide: continue or return early?

    # Optional: dump to JSON file (not recommended in production)
    # json_file = f"TEMP_DUMP_{project_code}_{client_id}.json"
    # try:
    #     with open(json_file, "w", encoding="utf-8") as f:
    #         json.dump(datasets, f, indent=2, default=str)
    # except Exception as e:
    #     print(f"Failed to write JSON dump: {e}")

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Accepted — processing {len(files)} file(s) in background",
            "project_code": project_code,
            "client_id": client_id,
            "task_ids": task_ids,        
            "file_count": len(files),
        }
    )

@app.get("/datasets")
def list_datasets(client_id: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    """Return a list of all uploaded datasets, optionally filtered by client_id."""
    try:

        q = db.query(Dataset)
        if client_id:
            q = q.filter(Dataset.client_id == client_id)
            print("START datasets_record-datasets_record-datasets_record")
            print(q.all())
            print("START datasets_record-datasets_record-datasets_record")

        datasets = {}
        project_codes = []
        for qs in q.all():
            datasets[qs.project_code] = {"datasets": []  } 

        for ds in q.all():
            datasets[qs.project_code] = {"datasets": []  } 
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
def get_schema(dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch dataset schema for a given dataset ID."""
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
def get_project(
    project_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch dataset schema for a given dataset ID."""
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
    current_user: dict = Depends(get_current_user),
    dataset_id: str = Query(...),
    x_column: str = Query(...),
    y_column: str = Query(...),
    agg: str = Query("sum"),
    db: Session = Depends(get_db)
):
    """Perform a simple aggregation for visualization (e.g., bar chart data)."""
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        result = aggregate_for_chart(ds.table_name, x_column, y_column, agg)
        return result
    finally:
        db.close()


@app.get("/preview/")
def preview(
    current_user: dict = Depends(get_current_user),
    dataset_id: str = Query(...), 
    limit: int = Query(100),
    db: Session = Depends(get_db)
    ):
    """Preview dataset contents (for dashboard table or quick inspection)."""
    try:
        ds = db.query(Dataset).filter(Dataset.dataset_id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

        df = fetch_table_preview(ds.table_name, limit)
        return {"columns": df.columns.tolist(), "rows": df.to_dict(orient="records")}
    finally:
        db.close()
# ======================
# HEALTH CHECK
# ======================
@app.get("/")
async def root():
    return {"message": "Intraq Auth & Email API", "status": "running"}