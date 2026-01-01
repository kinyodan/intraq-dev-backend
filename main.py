from fastapi import FastAPI, Request, Form, HTTPException, Depends, BackgroundTasks, Query, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from jose import jwt
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
from db import SessionLocal, engine
from models import Base, Dataset, DatasetMeta
from schemas import DatasetCreateResponse, DatasetInfo

# Ensure metadata DB tables exist
Base.metadata.create_all(bind=engine)

# ======================
# CONFIG
# ======================
JWT_SECRET = "replace-this-with-long-random-secret"
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE = 300             # 5 minutes
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

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="Intraq - Dynamic Dataset Ingest & Visualization API")

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
def generate_client_id():
    return f"CL{shortuuid.ShortUUID().random(length=8).upper()}"

def create_token_payload(user, extra=None, expires=ACCESS_TOKEN_EXPIRE):
    iat = int(time.time())
    exp = iat + expires
    payload = {"iss": ISSUER, "sub": user["sub"], "iat": iat, "exp": exp}
    if extra: payload.update(extra)
    return payload

def create_jwt(payload, expires_in=ACCESS_TOKEN_EXPIRE):
    iat = int(time.time())
    exp = iat + expires_in
    data = {"iss": ISSUER, "iat": iat, "exp": exp, **payload}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)

# ======================
# EXISTING AUTH ENDPOINTS
# ======================
@app.post("/signup")
async def signup(username: str = Form(...), password: str = Form(...), email: str = Form(...)):
    if username in USERS or any(u["email"].lower() == email.lower() for u in USERS.values()):
        raise HTTPException(status_code=400, detail="Username or email already exists")

    client_id = generate_client_id()

    USERS[username] = {
        "username": username,
        "password": pwd_ctx.hash(password),
        "sub": f"user-{len(USERS) + 1}",
        "email": email.lower(),
        "client_id": client_id,
    }

    return {
        "message": "User created successfully", 
        "username": username, 
        "email": email,
        "client_id": client_id
    }

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...),
                client_id: str = Form(None), redirect_uri: str = Form(None),
                state: str = Form(None), code_challenge: str = Form(None),
                code_challenge_method: str = Form(None)):
    identifier = username.strip().lower()
    user = USERS.get(identifier) or next((u for u in USERS.values() if u["email"] == identifier), None)
    if not user or not pwd_ctx.verify(password, user["password"]):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Invalid credentials",
                "message": "Username or password is incorrect"
            }
        )

    session_id = secrets.token_urlsafe(32)
    SESSIONS[session_id] = {"user": user, "expires": time.time() + REFRESH_TOKEN_EXPIRE}

    code = secrets.token_urlsafe(32)
    AUTH_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "user": user,
        "expires_at": time.time() + 300
    }

    q = {"code": code}
    print("redirect_uri")
    print(redirect_uri)

    if state: 
        q["state"] = state

    # Build the redirect URL that frontend will use
    redirect_url = redirect_uri + "?" + urllib.parse.urlencode(q)

    # Return JSON with all authentication information
    response_data = {
        "success": True,
        "message": "Authentication successful",
        "redirect_uri": redirect_url,  # The URL frontend should redirect to
        "auth_data": {
            "session_id": session_id,
            # Include any other auth tokens/data
            "access_token": q.get("access_token", ""),
            "token_type": q.get("token_type", "bearer"),
            "expires_in": q.get("expires_in", 3600),
            "scope": q.get("scope", ""),
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

    # Still set the cookie on backend response
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

class TokenRequest(BaseModel):
    grant_type: str
    code: str = None
    redirect_uri: str = None
    client_id: str = None
    code_verifier: str = None
    refresh_token: str = None

@app.post("/token")
async def token(req: TokenRequest):

    if req.grant_type == "authorization_code":
        code_data = AUTH_CODES.pop(req.code, None)
        if not code_data or code_data["expires_at"] < time.time():
            raise HTTPException(status_code=400, detail="Invalid or expired code")

        if code_data.get("code_challenge"):
            if not req.code_verifier:
                raise HTTPException(status_code=400, detail="PKCE required")
            v = hashlib.sha256(req.code_verifier.encode()).digest()
            expected = base64.urlsafe_b64encode(v).rstrip(b"=").decode()
            if expected != code_data["code_challenge"]:
                raise HTTPException(status_code=400, detail="PKCE verification failed")

        user = code_data["user"]
        access = create_token_payload(user, extra={"scope": "openid"}, expires=ACCESS_TOKEN_EXPIRE)
        refresh = secrets.token_urlsafe(48)
        REFRESH_TOKENS[refresh] = {"user": user, "expires": time.time() + REFRESH_TOKEN_EXPIRE}
        user_data = {"username": user["username"], "client_id": user["client_id"]}
        return {
            "access_token": jwt.encode(access, JWT_SECRET, algorithm=JWT_ALG),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE,
            "refresh_token": refresh,
            "user": user_data
        }

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

# ======================
# NEW EMAIL ENDPOINTS
# ======================
@app.post("/api/emails/send-bulk", response_model=EmailResponse)
async def send_bulk_emails(
    request: BulkEmailRequest,
    background_tasks: BackgroundTasks
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
        return {"success": True, "message": "Test email sent successfully", "message_id": result.message_id}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {result.error}")

@app.get("/api/emails/templates/{template_type}")
async def get_template_preview(template_type: str):
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
# ======================
# HEALTH CHECK
# ======================
@app.get("/")
async def root():
    return {"message": "Intraq Auth & Email API", "status": "running"}