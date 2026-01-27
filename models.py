# models.py

from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, func,ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timedelta
from pytz import utc
from sqlalchemy.orm import relationship  
# Create a base class for all models
Base = declarative_base()

class Client(Base):
    """
    Represents a client in the system.
    Used for onboarding via WhatsApp.
    """
    __tablename__ = "clients"

    # Client ID (the code they send in "onboard:ABC123")
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    client_id = Column(String, unique=True, nullable=False)

    # Phone number from WhatsApp (e.g., "919876543210")
    phone_number = Column(String, unique=True, nullable=True)

    # Whether the client has completed onboarding
    onboarded = Column(Boolean, default=False)

    # Optional: add more fields later if needed
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    client_id = Column(String, index=True, nullable=False)
    project_name = Column(String, nullable=False)
    project_code = Column(String, nullable=True)
    status = Column(String, nullable=False, default="in-progress")
    due_date = Column(String, nullable=False,
    default=lambda: (datetime.utcnow() + timedelta(days=30)).isoformat())    
    processing_errors = Column(JSON, nullable=False, default={})
    assigned_to = Column(String, nullable=False, default="")
    assigned_by = Column(String, nullable=False, default="")
    dataset_id = Column(String, nullable=False)  
    table_name = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    schema = Column(JSON, nullable=False) 
    meta = Column(JSON, nullable=True)     
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class DatasetMeta(Base):
    __tablename__ = "dataset_meta"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_code = Column(String, nullable=False, default=0)
    project_total_rows =Column(Integer, nullable=False, default=0)
    project_total_errors =Column(Integer, nullable=False, default=0)
    project_errors = Column(JSON, nullable=True, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class User(Base):
    """
    Represents a user in the system.
    Used for authentication and signup.
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)  # Hashed password
    client_id = Column(String, unique=True, nullable=False, index=True)  # Generated client ID
    sub = Column(String, unique=True, nullable=False)  # e.g., "user-1"
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships (optional - add if needed later)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    auth_codes = relationship("AuthCode", back_populates="user", cascade="all, delete-orphan")
    packages = relationship("Package", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """Stores active user sessions (replaces SESSIONS dict)"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    user = relationship("User", back_populates="sessions")

class AuthCode(Base):
    """Stores temporary authorization codes (replaces AUTH_CODES dict)"""
    __tablename__ = "auth_codes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    client_id = Column(String, nullable=True)
    redirect_uri = Column(String, nullable=True)
    code_challenge = Column(String, nullable=True)
    code_challenge_method = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    user = relationship("User", back_populates="auth_codes")

class Package(Base):
    """ Stores the client packages selected"""
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String, ForeignKey("users.client_id"), nullable=False)
    package_name = Column(String, nullable=False)
    previous_package = Column(String, nullable=False)
    started_with = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="packages")

