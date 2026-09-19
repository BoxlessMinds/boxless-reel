"""Data access repositories."""

from sqlalchemy.orm import Session

from src.repositories.cross_chat_repository import CrossChatRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.google_oauth_repository import GoogleOAuthRepository
from src.repositories.invitation_repository import InvitationRepository
from src.repositories.plan_repository import PlanRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.quota_repository import QuotaRepository
from src.repositories.refresh_token_repository import RefreshTokenRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.settings_repository import SettingsRepository
from src.repositories.system_settings_repository import SystemSettingsRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.repositories.user_repository import UserRepository
from src.repositories.watch_history_repository import WatchHistoryRepository

__all__ = [
    "CrossChatRepository",
    "DocumentRepository",
    "GoogleOAuthRepository",
    "InvitationRepository",
    "PlanRepository",
    "PlaylistRepository",
    "QuotaRepository",
    "RefreshTokenRepository",
    "SessionRepository",
    "SettingsRepository",
    "SystemSettingsRepository",
    "TranscriptRepository",
    "UserRepository",
    "WatchHistoryRepository",
    "get_cross_chat_repository",
    "get_document_repository",
    "get_google_oauth_repository",
    "get_invitation_repository",
    "get_plan_repository",
    "get_playlist_repository",
    "get_quota_repository",
    "get_refresh_token_repository",
    "get_session_repository",
    "get_settings_repository",
    "get_system_settings_repository",
    "get_transcript_repository",
    "get_user_repository",
    "get_watch_history_repository",
]


def get_transcript_repository(db: Session) -> TranscriptRepository:
    """Factory function for TranscriptRepository."""
    return TranscriptRepository(db)


def get_session_repository(db: Session) -> SessionRepository:
    """Factory function for SessionRepository."""
    return SessionRepository(db)


def get_settings_repository(db: Session) -> SettingsRepository:
    """Factory function for SettingsRepository."""
    return SettingsRepository(db)


def get_user_repository(db: Session) -> UserRepository:
    """Factory function for UserRepository."""
    return UserRepository(db)


def get_invitation_repository(db: Session) -> InvitationRepository:
    """Factory function for InvitationRepository."""
    return InvitationRepository(db)


def get_refresh_token_repository(db: Session) -> RefreshTokenRepository:
    """Factory function for RefreshTokenRepository."""
    return RefreshTokenRepository(db)


def get_document_repository(db: Session) -> DocumentRepository:
    """Factory function for DocumentRepository."""
    return DocumentRepository(db)


def get_google_oauth_repository(db: Session) -> GoogleOAuthRepository:
    """Factory function for GoogleOAuthRepository."""
    return GoogleOAuthRepository(db)


def get_system_settings_repository(db: Session) -> SystemSettingsRepository:
    """Factory function for SystemSettingsRepository."""
    return SystemSettingsRepository(db)


def get_cross_chat_repository(db: Session) -> CrossChatRepository:
    """Factory function for CrossChatRepository."""
    return CrossChatRepository(db)


def get_playlist_repository(db: Session) -> PlaylistRepository:
    """Factory function for PlaylistRepository."""
    return PlaylistRepository(db)


def get_plan_repository(db: Session) -> PlanRepository:
    """Factory function for PlanRepository."""
    return PlanRepository(db)


def get_quota_repository(db: Session) -> QuotaRepository:
    """Factory function for QuotaRepository."""
    return QuotaRepository(db)


def get_watch_history_repository(db: Session) -> WatchHistoryRepository:
    """Factory function for WatchHistoryRepository."""
    return WatchHistoryRepository(db)
