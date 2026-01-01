# db.py (updated)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./intraq_meta.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Import models to register them with Base
from models import Base  # <-- Add this line

# Create all tables (safe to run every time - won't recreate existing ones)
Base.metadata.create_all(bind=engine)