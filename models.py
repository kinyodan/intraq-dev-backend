# models.py

from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime 
from pytz import utc

# Create a base class for all models
Base = declarative_base()

class Client(Base):
    """
    Represents a client in the system.
    Used for onboarding via WhatsApp.
    """
    __tablename__ = "clients"

    # Client ID (the code they send in "onboard:ABC123")
    id = Column(String, primary_key=True)

    # Phone number from WhatsApp (e.g., "919876543210")
    phone_number = Column(String, unique=True, nullable=True)

    # Whether the client has completed onboarding
    onboarded = Column(Boolean, default=False)

    # Optional: add more fields later if needed
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class Dataset(Base):
    __tablename__ = "datasets"

    client_id = Column(String, index=True, nullable=False)
    project_name = Column(String, nullable=False)
    project_code = Column(String, nullable=True)
    status = Column(String, nullable=False, default="in-progress")
    due_date = Column(String, nullable=False, default=datetime.utcnow )
    processing_errors = Column(JSON, nullable=False, default={})
    assigned_to = Column(String, nullable=False, default="")
    assigned_by = Column(String, nullable=False, default="")
    dataset_id = Column(String, primary_key=True)  # UUID as string
    table_name = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    schema = Column(JSON, nullable=False)  # Stores list of {"name": ..., "dtype": ...}
    meta = Column(JSON, nullable=True)     # Optional extra metadata

    # Optional: add timestamps later
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class DatasetMeta(Base):
    __tablename__ = "dataset_meta"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_code = Column(String, nullable=False, default=0)
    project_total_rows =Column(Integer, nullable=False, default=0)
    project_total_errors =Column(Integer, nullable=False, default=0)
    project_errors = Column(JSON, nullable=True, default={})
