# API routers
from src.routers.admin import router as admin_router
from src.routers.agent import session_router, transcript_agent_router
from src.routers.auth import router as auth_router
from src.routers.cross_chat import cross_chat_router
from src.routers.documents import router as documents_router
from src.routers.google_auth import router as google_auth_router
from src.routers.invitations import router as invitations_router
from src.routers.plans import router as plans_router
from src.routers.playlists import router as playlists_router
from src.routers.settings import router as settings_router
from src.routers.transcripts import router as transcripts_router
from src.routers.watch_history import router as watch_history_router

__all__ = [
    "transcripts_router",
    "transcript_agent_router",
    "session_router",
    "cross_chat_router",
    "documents_router",
    "settings_router",
    "auth_router",
    "invitations_router",
    "admin_router",
    "google_auth_router",
    "playlists_router",
    "plans_router",
    "watch_history_router",
]
