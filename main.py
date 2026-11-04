from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import paginate , add_pagination
from fastapi_pagination.utils import disable_installed_extensions_check

# ============================================================
# APPLICATION ROUTERS
# ============================================================
from routers import authentication


app = FastAPI(title="Intraq - Dynamic Dataset Ingest & Visualization API")
add_pagination(app)

# Ensure metadata DB tables exist
#Base.metadata.create_all(bind=engine)

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # For local development
        "http://localhost:3001",      # For local development
        "http://127.0.0.1:3000",      # For local development
        "http://127.0.0.1",      # For local development
        "https://intraqapp.simokai.com",
        "https://intraq.simokai.com",
        "https://intraq-ui.vercel.app",
        "https://intraq-dashboard.vercel.app",
        "https://dashboard.intraq.simokai.com",
        "https://www.intraq.pro",
        "https://dashboard.intraq.pro"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    authentication.router,
    prefix="/api/auth", 
    tags=["Authentication"]
)

# ======================
# HEALTH CHECK
# ======================
@app.get("/")
async def root():
    return {"message": "Intraq Auth & Email API", "status": "running"}