# models.py
import os
from sqlalchemy import Column, Integer, String, DateTime, Boolean, create_engine, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sqlalchemy

Base = declarative_base()
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./whatsapp.db")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True)
    name = Column(String)
    phone_number = Column(String, index=True)
    onboarded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# For portability, use JSON if DB supports it, else Text
def JSONType():
    try:
        # if PostgreSQL -> use native JSON
        from sqlalchemy.dialects.postgresql import JSON as PGJSON
        return PGJSON
    except Exception:
        return Text

class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, index=True)
    dataset_id = Column(String, unique=True, index=True)
    table_name = Column(String, unique=True)
    filename = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    schema = Column(JSONType())  # list of {name, dtype}
    meta = Column(Text, nullable=True)  # extra info as json string

def create_db():
    engine = sqlalchemy.create_engine(os.getenv("DATABASE_URL", "sqlite:///./intraq_meta.db"), connect_args={"check_same_thread": False} if os.getenv("DATABASE_URL","").startswith("sqlite") else {})
    Base.metadata.create_all(bind=engine)
