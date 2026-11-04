"""Password and JWT utilities. Connect token validation to your actual user lookup."""
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from core.config import settings

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def create_access_token(subject: str, expires_delta: timedelta | None = None, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {"sub": subject, "iat": now, "exp": now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))}
    if extra_claims:
        if {"sub", "iat", "exp"}.intersection(extra_claims):
            raise ValueError("Cannot override protected JWT claims")
        claims.update(extra_claims)
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc
