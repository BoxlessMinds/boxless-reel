"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings

# Export API keys to os.environ for libraries that read directly from environment
# (e.g., LanceDB's OpenAI embeddings)
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
from src.database import Base, engine
from src.routers import (
    admin_router,
    auth_router,
    cross_chat_router,
    documents_router,
    google_auth_router,
    invitations_router,
    plans_router,
    playlists_router,
    session_router,
    settings_router,
    transcript_agent_router,
    transcripts_router,
    watch_history_router,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info("Starting YouTube Transcript API")
    if settings.jwt_secret_key == "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32":
        logger.warning(
            "JWT_SECRET_KEY is using the default placeholder — "
            "set a secure value for production (generate with: openssl rand -hex 32)"
        )
    logger.info("Log level: %s", settings.log_level)
    logger.debug("Database URL: %s", settings.database_url)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")
    if settings.agents_enabled:
        logger.info("Agent features enabled (LLM provider: %s)", settings.default_llm_provider)
    else:
        logger.info("Agent features disabled (no API keys configured)")
    yield
    # Shutdown
    logger.info("Shutting down YouTube Transcript API")


app = FastAPI(
    title="YouTube Transcript API",
    description="RESTful API for extracting, storing, and managing YouTube video transcripts",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - configured via ALLOWED_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(
    transcripts_router,
    prefix="/api/transcripts",
    tags=["transcripts"],
)

# Agent routers for transcript-scoped endpoints
app.include_router(
    transcript_agent_router,
    prefix="/api/transcripts",
    tags=["agent"],
)

# Agent routers for session-scoped endpoints
app.include_router(
    session_router,
    prefix="/api/sessions",
    tags=["sessions"],
)

# Settings router
app.include_router(
    settings_router,
    prefix="/api/settings",
    tags=["settings"],
)

# Auth routers
app.include_router(
    auth_router,
    prefix="/api/auth",
    tags=["auth"],
)

app.include_router(
    invitations_router,
    prefix="/api/invitations",
    tags=["invitations"],
)

app.include_router(
    admin_router,
    prefix="/api/admin",
    tags=["admin"],
)

# Documents router
app.include_router(
    documents_router,
    prefix="/api/documents",
    tags=["documents"],
)

# Cross-chat router
app.include_router(
    cross_chat_router,
    prefix="/api/cross-chat",
    tags=["cross-chat"],
)

# Google OAuth (YouTube account connection) router
app.include_router(
    google_auth_router,
    prefix="/api/youtube-auth",
    tags=["youtube-auth"],
)

# Playlist sync & library view router
app.include_router(
    playlists_router,
    prefix="/api/playlists",
    tags=["playlists"],
)

# Plan/apply execution engine router
app.include_router(
    plans_router,
    prefix="/api/plans",
    tags=["plans"],
)

# Watch-history import router (Google Takeout purge-watched feature)
app.include_router(
    watch_history_router,
    prefix="/api/watch-history",
    tags=["watch-history"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy"}


# =============================================================================
# Static File Serving for Production (Replit)
# =============================================================================
# Serve the frontend build when running in production without nginx
frontend_dist = Path(__file__).parent.parent / "youtube-transcript-ui" / "dist"

if frontend_dist.exists():
    logger.info("Frontend build found, serving static files from %s", frontend_dist)

    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/favicon.svg")
    async def favicon():
        """Serve favicon."""
        favicon_path = frontend_dist / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        return FileResponse(frontend_dist / "favicon.ico", media_type="image/x-icon")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        # Don't intercept API routes or known endpoints
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            return None

        # Check if the file exists (for direct file requests)
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Return index.html for SPA client-side routing
        return FileResponse(frontend_dist / "index.html")
else:
    logger.debug("No frontend build found at %s", frontend_dist)
