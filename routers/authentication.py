from core.imports import *
from fastapi import APIRouter

router = APIRouter()

bearer_scheme = HTTPBearer()

# Assume pwd_ctx is your password hasher (e.g., passlib)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ======================
# CONFIG
# ======================
JWT_SECRET = "replace-this-with-long-random-secret"
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE = 60 * 60 * 24 * 7              # 1 minutes
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24 * 7   # 1 day
ISSUER = "https://auth.nx.com"        # your auth server domain
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


# ======================
# IN-MEMORY STORES
# ======================
USERS = {}
AUTH_CODES = {}
SESSIONS = {}
REFRESH_TOKENS = {}

def get_db():
    print("getting db..")
    db = SessionLocal()
    print(db)
    try:
        yield db
    finally:
        db.close()

# ======================
# EXISTING AUTH HELPERS
# ======================
async def login_to_remote_api(
    email: str, 
    password: str, 
    base_url: str = os.getenv("FLOWBRIDGE_API_BASE_URL", "http://localhost:8000")
):
    """
    Calls your main FastAPI /login endpoint and returns the full response.
    """
    url = f"{base_url}/login"
    
    form_data = {
        "username": email.strip().lower(),   # backend expects 'username'
        "password": password,
        #"client_id": "multiwoven-app",       # optional, adjust as needed
        #"redirect_uri": "https://your-multiwoven-domain.com/auth/callback",  # optional
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url, 
            data=form_data,
            timeout=30.0
        )

    try:
        result = response.json()
    except:
        result = {"raw_text": response.text}

    return {
        "status_code": response.status_code,
        "success": response.status_code == 200 and result.get("success", False),
        "data": result,
        "cookies": dict(response.cookies),   # if any cookies are set
        "headers": dict(response.headers)
    } 


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


def get_admin_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Admin-only dependency - checks if user is admin based on env vars"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(status_code=401, detail="Token expired")
        
        # Get user from database to check client_id and email
        db = next(get_db())
        user = db.query(User).filter(User.sub == username).first()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Check if user is admin
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_client_id = os.getenv("ADMIN_CLIENT_ID")
        
        is_admin = False
        if admin_email and user.email == admin_email:
            is_admin = True
        if admin_client_id and user.client_id == admin_client_id:
            is_admin = True
        
        if not is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        return {"sub": username, "email": user.email, "client_id": user.client_id}
    except HTTPException:
        raise
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

@router.post("/token")
async def token(req: TokenRequest, db: Session = Depends(get_db)):

    if req.grant_type == "authorization_code":
        
        # Find authorization code  
        code_data = db.query(AuthCode).filter(
            (AuthCode.code == req.code)
        ).first()

        # code_data = AUTH_CODES.pop(req.code, None)
        # if not code_data or code_data["expires_at"] < time.time():
            # raise HTTPException(status_code=400, detail="Invalid or expired code")
        print(code_data)
            
        if code_data and code_data.code_challenge:
            if not req.code_verifier:
                raise HTTPException(status_code=400, detail="PKCE required")
            v = hashlib.sha256(req.code_verifier.encode()).digest()
            expected = base64.urlsafe_b64encode(v).rstrip(b"=").decode()
            if expected != code_data.code_challenge:
                raise HTTPException(status_code=400, detail="PKCE verification failed")
            print(code_data)        

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

@router.get("/session")
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

@router.post("/signup")
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

    # Create GCS bucket + subfolders BEFORE saving user (or after - your choice)
    try:
        bucket_name = create_user_gcs_structure(client_id)
    except Exception as gcs_error:
        # Optional: You can log it and continue, or fail the signup
        print(f"Warning: GCS setup failed but continuing signup: {gcs_error}")
        bucket_name = None

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

    # Find user by username OR email
    user = db.query(User).filter(
        (User.username == username) | (User.email == email.lower())
    ).first()

    return {
        "message": "User created successfully",
        "username": user.username,
        "email": user.email,
        "client_id": user.client_id,
        "gcs_bucket": bucket_name ,
    }

@router.post("/login")
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
    
    print("..................")
    print(user)
    print(password)
    print(user.password)
    print("..................")

    if not user or not pwd_ctx.verify(password, user.password):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "Invalid credentials",
                "message": "Username or password is incorrect"
            }
        )

    #try:
        #bucket_name = create_user_gcs_structure(user.client_id)
    #except Exception as gcs_error:
        # Optional: You can log it and continue, or fail the signup
        #print(f"Warning: GCS setup failed but continuing signup: {gcs_error}")
        #bucket_name = None

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

    # Example in a Rails controller or another FastAPI route
    # flowbridge_result = await login_to_remote_api(
    #     email=username,
    #     password=password,
    # )

    # if result["success"]:
    #     print("Login successful!")
    #     print("Redirect URL:", result["data"].get("redirect_uri"))
    #     print("Session ID:", result["data"]["auth_data"]["session_id"])
    # else:
    #     print("Login failed:", result["data"])

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
        },
        # "flowbridge_auth_data": {
        #     "auth_data": flowbridge_result
        # }
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

@router.get("/authorize")
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

@router.get("/verify-token")
async def verify_token_endpoint(authorization: str = Header(None)):
    """
    Verify JWT access token for internal microservices.
    Header:
        Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization format"
        )

    token = authorization.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALG]
        )

        return {
            "valid": True,
            "user": {
                "sub": payload.get("sub"),
                "username": payload.get("username"),
                "client_id": payload.get("client_id"),
                "scope": payload.get("scope"),
                "exp": payload.get("exp")
            }
        }

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token expired"
        )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token verification failed: {str(e)}"
        )

@router.post("/set_package")
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

@router.get("/packages/{client_id}", response_model=PackagesResponse)
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