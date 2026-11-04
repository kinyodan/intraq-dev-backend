from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import paginate , add_pagination
from fastapi_pagination.utils import disable_installed_extensions_check
from routers import authentication

# 1. ADD THESE MISSING IMPORTS HERE
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
import time
import hashlib
import base64
import os 
import secrets
from passlib.context import CryptContext
from passlib.hash import bcrypt
from fastapi.security import (
    OAuth2PasswordBearer, 
    OAuth2PasswordRequestForm, 
    HTTPBearer, 
    HTTPAuthorizationCredentials
)
from jose import (
    jwt, 
    JWTError, 
    ExpiredSignatureError
)
from pwdlib import PasswordHash

# Replace 'your_app_package.auth_module' with the actual python path to your auth router file


# Import your router, schemas, and helpers here
# from your_module import router, TokenRequest, JWT_SECRET, JWT_ALG, ACCESS_TOKEN_EXPIRE, get_db

# Setup a dummy app to host the router for testing
app = FastAPI()
app.include_router(authentication.router)


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
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")


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
    try:
        yield db
    finally:
        db.close()


# Dummy Models to support execution if needed by your schema checks
class MockUser:
    def __init__(self, id=1, username="testuser", sub="user_sub_123", client_id="CL_ABC123", email="user@test.com"):
        self.id = id
        self.username = username
        self.sub = sub
        self.client_id = client_id
        self.email = email

class MockAuthCode:
    def __init__(self, code, user_id=1, code_challenge=None):
        self.code = code
        self.user_id = user_id
        self.code_challenge = code_challenge

@pytest.fixture
def mock_db():
    """Mock standard SQLAlchemy Session tracking query chains."""
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    return db

@pytest.fixture
def client(mock_db):
    """
    Forces FastAPI to pass your test's database session directly into the endpoints,
    ensuring they both read and write from the exact same mock instance.
    """
    # Define the override function that yields your test session
    def _get_db_override():
        yield mock_db
    
    # Force FastAPI to replace the router's real get_db call with our override
    app.dependency_overrides[authentication.get_db] = _get_db_override
    
    yield TestClient(app)
    
    # Clean up after the test completes so it doesn't leak into other suites
    app.dependency_overrides.clear()


# =====================================================================
# ENDPOINT: POST /token TESTS
# =====================================================================

def test_token_auth_code_grant_success(client, mock_db):
    # Setup test variables
    test_code = "auth_code_xyz"
    mock_user = MockUser()
    mock_auth_code = MockAuthCode(code=test_code, user_id=mock_user.id)
    
    # Track the exact query target to ensure code_data is never None
    def dynamic_first_resolver():
        # Check the last filter query argument used on our mock
        filter_args = mock_db.filter.call_args[0][0]
        # Convert the binary/SQL expression evaluation to string to identify the table
        filter_str = str(filter_args)
        
        if "auth_code" in filter_str.lower() or "code" in filter_str.lower():
            return mock_auth_code
        if "user" in filter_str.lower():
            return mock_user
        return None

    mock_db.first.side_effect = dynamic_first_resolver

    payload = {
        "grant_type": "authorization_code",
        "code": test_code
    }
    
    response = client.post("/token", json=payload)
    print(response.json())
    
    assert response.status_code == 200
    res_data = response.json()
    assert "access_token" in res_data
    assert res_data["token_type"] == "bearer"
    assert "refresh_token" in res_data
    assert res_data["user"]["username"] == "testuser"


def test_token_auth_code_pkce_success(client, mock_db):
    test_code = "auth_code_pkce"
    code_verifier = "secret_verifier_string_long_enough_for_pkce_verification"
    
    # Derive code challenge (SHA256 URL-safe Base64 encoded)
    v = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(v).rstrip(b"=").decode()
    
    mock_user = MockUser()
    mock_auth_code = MockAuthCode(code=test_code, user_id=mock_user.id, code_challenge=code_challenge)
    mock_db.first.side_effect = [mock_auth_code, mock_user]

    payload = {
        "grant_type": "authorization_code",
        "code": test_code,
        "code_verifier": code_verifier
    }
    
    response = client.post("/token", json=payload)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_token_auth_code_pkce_failure(client, mock_db):
    test_code = "auth_code_pkce_fail"
    mock_auth_code = MockAuthCode(code=test_code, user_id=1, code_challenge="expected_challenge_hash")
    mock_db.first.return_value = mock_auth_code

    payload = {
        "grant_type": "authorization_code",
        "code": test_code,
        "code_verifier": "wrong_verifier"
    }
    
    response = client.post("/token", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "PKCE verification failed"


def test_token_auth_code_missing_user_attribute(client, mock_db):
    test_code = "auth_code_no_user"
    mock_auth_code = MockAuthCode(code=test_code, user_id=None) # Implicitly misses user_id field
    mock_db.first.return_value = mock_auth_code

    payload = {
        "grant_type": "authorization_code",
        "code": test_code
    }
    
    response = client.post("/token", json=payload)
    assert response.status_code == 400
    assert "Missing attribute user" in response.json()["detail"]


def test_token_refresh_token_grant_success(client):
    from core.routers.auth import REFRESH_TOKENS  # Adjust namespace path to find your global dict
    
    mock_user = MockUser()
    fake_refresh_token = secrets.token_urlsafe(48)
    
    # Pre-populate in-memory REFRESH_TOKENS store
    REFRESH_TOKENS[fake_refresh_token] = {
        "user": mock_user,
        "expires": time.time() + 1000
    }

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": fake_refresh_token
    }
    
    response = client.post("/token", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert "access_token" in res_data
    assert "refresh_token" in res_data
    assert res_data["refresh_token"] != fake_refresh_token  # Verified that old token got rotated and destroyed


def test_token_refresh_token_expired(client):
    from core.routers.auth import REFRESH_TOKENS
    
    expired_token = "expired_refresh_token"
    REFRESH_TOKENS[expired_token] = {
        "user": MockUser(),
        "expires": time.time() - 1000 # Force expiration timestamp match rule
    }

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": expired_token
    }
    
    response = client.post("/token", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid refresh token"


def test_token_unsupported_grant_type(client):
    payload = {
        "grant_type": "client_credentials"
    }
    response = client.post("/token", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported grant_type"


# =====================================================================
# HELPER & DEPENDENCY SCHEME INLINE TESTS
# =====================================================================

def test_get_current_user_dependency_valid():
    # FIX: Change from core.routers.auth to routers.authentication
    # (or since it's imported at the top now, you can even comment out these local imports)
    from routers.authentication import get_current_user, JWT_SECRET, JWT_ALG
    
    iat = int(time.time())
    token_payload = {"sub": "test_subj", "iat": iat, "exp": iat + 500}
    encoded_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALG)
    
    mock_credentials = MagicMock()
    mock_credentials.credentials = encoded_token
    
    user = get_current_user(mock_credentials)
    assert user["sub"] == "test_subj"


def test_get_current_user_dependency_expired():
    # FIX: Change from core.routers.auth to routers.authentication
    from routers.authentication import get_current_user, JWT_SECRET, JWT_ALG
    
    token_payload = {"sub": "test_subj", "iat": int(time.time()) - 200, "exp": int(time.time()) - 50}
    encoded_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALG)
    
    mock_credentials = MagicMock()
    mock_credentials.credentials = encoded_token
    
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(mock_credentials)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail

