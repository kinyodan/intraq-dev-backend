from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt
from passlib.context import CryptContext
import secrets, time, urllib.parse, re, hashlib, base64
import shortuuid

# ======================
# CONFIG
# ======================
JWT_SECRET = "replace-this-with-long-random-secret"
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE = 300             # 5 minutes
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24   # 1 day
ISSUER = "https://auth.nx.com"        # your auth server domain

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

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://landing.nx.com",
        "https://app1.nx.com",
        "http://localhost:3000",      # For local development
        "http://127.0.0.1:3000",      # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# HELPERS
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
# SIGNUP
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


# ======================
# LOGIN (Form-based for /authorize flow)
# ======================
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...),
                client_id: str = Form(None), redirect_uri: str = Form(None),
                state: str = Form(None), code_challenge: str = Form(None),
                code_challenge_method: str = Form(None)):
    identifier = username.strip().lower()
    user = USERS.get(identifier) or next((u for u in USERS.values() if u["email"] == identifier), None)
    if not user or not pwd_ctx.verify(password, user["password"]):
        return HTMLResponse("<html><body>Invalid login. <a href='javascript:history.back()'>Back</a></body></html>", status_code=401)

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
    if state: q["state"] = state
    dest = redirect_uri + "?" + urllib.parse.urlencode(q)
    resp = RedirectResponse(dest)
    resp.set_cookie("auth_session", session_id, httponly=True, secure=True,
                    samesite="none", domain=".nx.com")  # 🔥 share across apps
    return resp


# ======================
# AUTHORIZE (Start of OAuth flow)
# ======================
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


# ======================
# TOKEN ENDPOINT
# ======================
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
        return {
            "access_token": jwt.encode(access, JWT_SECRET, algorithm=JWT_ALG),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE,
            "refresh_token": refresh
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


# ======================
# SESSION CHECK (SSO)
# ======================
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
