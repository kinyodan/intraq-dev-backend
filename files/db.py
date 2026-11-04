# db.py (updated)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import os
from dotenv import load_dotenv

load_dotenv()

# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./intraq_meta.db")
# TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

# engine = create_engine(
#     DATABASE_URL,
#     connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# )

# SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# # Import models to register them with Base
# from models import Base  # <-- Add this line

# # Create all tables (safe to run every time - won't recreate existing ones)
# Base.metadata.create_all(bind=engine)

# === Option A: Pure remote connection (no local file, simple) ===
# Recommended if you don't need offline tolerance or very high read speed
TURSO_HOST = os.getenv("TURSO_DATABASE_URL") #,"intraq-dataops-kinyodan.aws-eu-west-1.turso.io")
TURSO_TOKEN = os.getenv("TURSO_TOKEN") #, "")
print("TURSO_HOST==TURSO_HOST")
print(TURSO_HOST)
print(TURSO_TOKEN)
print("TURSO_HOST==TURSO_HOST")
DATABASE_URL = f"sqlite+libsql://{TURSO_HOST}?secure=true"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "auth_token": TURSO_TOKEN,
    }
)

# === Option B: Embedded replica (local file + sync) – better performance ===
# Uncomment this block instead of the above if you want local caching/sync
# local_db_path = "intraq_local.db"  # will be created in project root
# DATABASE_URL = f"sqlite+libsql:///{local_db_path}"
# engine = create_engine(
#     DATABASE_URL,
#     connect_args={
#         "auth_token": TURSO_TOKEN,
#         "sync_url": f"libsql://{TURSO_HOST}",
#     }
# )
# # Optional: sync on startup (or call periodically)
# @app.on_event("startup")  # if in FastAPI
# def sync_on_startup():
#     with engine.connect() as conn:
#         conn.execute("SELECT 1")  # triggers sync internally in some cases
#     # or use libsql_client directly for explicit sync if needed

SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

# Import models to register them with Base
from models import Base  # <-- already good

# Create all tables (safe - idempotent)
Base.metadata.create_all(bind=engine)