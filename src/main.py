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
def resolve_build_file(dist_root: Path, requested: str) -> Path | None:
    """
    Resolve a requested path to a file inside the build folder.

    Args:
        dist_root: The resolved (absolute) frontend build folder
        requested: The path taken from the request URL

    Returns:
        The resolved file path if it is a regular file inside the build folder,
        otherwise None
    """
    try:
        candidate = (dist_root / requested).resolve()
    except (OSError, ValueError) as exc:
        logger.debug("Could not resolve requested path: %s", exc)
        return None
    if candidate.is_relative_to(dist_root) and candidate.is_file():
        return candidate
    return None


def register_frontend_routes(target_app: FastAPI, dist_dir: Path) -> None:
    """
    Register routes that serve the built frontend from a build folder.

    Args:
        target_app: The FastAPI application to add the routes to
        dist_dir: The frontend build folder (must contain index.html and assets/)
    """
    dist_root = dist_dir.resolve()

    # Serve static assets (JS, CSS, images)
    target_app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @target_app.get("/favicon.svg")
    async def favicon():
        """Serve favicon."""
        favicon_path = dist_dir / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        return FileResponse(dist_dir / "favicon.ico", media_type="image/x-icon")

    @target_app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        # Don't intercept API routes or known endpoints
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            return None

        # Serve the file only if it exists inside the build folder
        file_path = resolve_build_file(dist_root, full_path)
        if file_path is not None:
            return FileResponse(file_path)

        # Return index.html for SPA client-side routing
        return FileResponse(dist_dir / "index.html")


# Serve the frontend build when running in production without nginx
frontend_dist = Path(__file__).parent.parent / "youtube-transcript-ui" / "dist"

if frontend_dist.exists():
    logger.info("Frontend build found, serving static files from %s", frontend_dist)
    register_frontend_routes(app, frontend_dist)
else:
    logger.debug("No frontend build found at %s", frontend_dist)
