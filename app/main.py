"""Vantage Risk — FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.db.base import init_db
from app.api.routes_auth import router as auth_router
from app.api.routes_securities import router as securities_router
from app.api.routes_portfolios import router as portfolios_router
from app.api.routes_risk import router as risk_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Vantage Risk",
    description="Portfolio Risk Analytics API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development, restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth_router)
app.include_router(securities_router)
app.include_router(portfolios_router)
app.include_router(risk_router)

# Serve the frontend static file
# On Render: repo root is parent.parent (app/main.py → app → vantage-risk-backend/)
# Locally it may be one level higher — check both locations
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # vantage-risk-backend/
_DASHBOARD = _PROJECT_ROOT / "risk_dashboard.html"
if not _DASHBOARD.exists():
    # Fallback: local dev where HTML is one dir above the backend
    _DASHBOARD = _PROJECT_ROOT.parent / "risk_dashboard.html"

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the risk dashboard as the root page."""
    return FileResponse(_DASHBOARD)


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Vantage Risk"}
