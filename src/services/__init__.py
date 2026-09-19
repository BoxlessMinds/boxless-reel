"""Business logic services."""

from sqlalchemy.orm import Session

from src.repositories import (
    CrossChatRepository,
    DocumentRepository,
    SessionRepository,
    TranscriptRepository,
)
from src.services.agent_service import AgentService, QueryResponse, SessionInfo
from src.services.auth_service import (
    AuthenticationError,
    AuthService,
    TokenError,
    get_auth_service,
)
from src.services.cross_chat_service import CrossChatService
from src.services.document_service import (
    DocumentIndexingError,
    DocumentNotFoundError,
    DocumentService,
    DocumentServiceError,
    FileTooLargeError,
    MaxDocumentsExceededError,
    UnsupportedFileTypeError,
)
from src.services.google_auth_service import (
    GoogleAuthService,
    GoogleAuthServiceError,
    GoogleAuthStateError,
    GoogleCredentialNotFoundError,
    GoogleTokenRefreshError,
    get_google_auth_service,
)
from src.services.exceptions import (
    AgentNotAvailableError,
    AgentServiceError,
    CrossChatSessionNotFoundError,
    CrossChatValidationError,
    IndexingError,
    InvalidVideoIdError,
    QueryExecutionError,
    SessionNotFoundError,
    TranscriptAlreadyExistsError,
    TranscriptNotAvailableError,
    TranscriptNotFoundError,
    VideoNotFoundError,
    YouTubeServiceError,
)
from src.services.invitation_service import (
    InvitationExistsError,
    InvitationLimitError,
    InvitationNotFoundError,
    InvitationService,
    get_invitation_service,
)
from src.services.plan_apply_service import (
    PlanApplyError,
    PlanNotFoundError,
    apply_plan,
)
from src.services.playlist_planning_service import (
    PlaylistPlanningService,
    get_playlist_planning_service,
)
from src.services.playlist_sync_service import (
    PlaylistSyncService,
    SyncResult,
    get_playlist_sync_service,
)
from src.services.quota_service import (
    DailyQuotaStatus,
    QuotaService,
    get_daily_quota_status,
    get_quota_service,
)
from src.services.watch_history_service import (
    InvalidTakeoutFileError,
    TakeoutFileTooLargeError,
    WatchHistoryService,
    WatchHistoryServiceError,
    get_watch_history_service,
)
from src.services.settings_service import SettingsService, get_settings_service
from src.services.system_settings_service import SystemSettingsService, get_system_settings_service
from src.services.transcript_service import TranscriptService
from src.services.user_service import (
    InvalidInvitationError,
    UserExistsError,
    UserService,
    get_user_service,
)
from src.services.youtube_data_service import (
    PermanentAPIError,
    QuotaExceededError,
    YouTubeDataService,
    YouTubeDataServiceError,
)
from src.services.youtube_service import YouTubeService

__all__ = [
    # Services
    "YouTubeService",
    "TranscriptService",
    "AgentService",
    "CrossChatService",
    "SettingsService",
    "SystemSettingsService",
    "AuthService",
    "UserService",
    "InvitationService",
    "DocumentService",
    "GoogleAuthService",
    "PlaylistSyncService",
    "PlaylistPlanningService",
    "QuotaService",
    "YouTubeDataService",
    "WatchHistoryService",
    # Agent data classes
    "SessionInfo",
    "QueryResponse",
    # Playlist sync data classes
    "SyncResult",
    # Quota data classes
    "DailyQuotaStatus",
    # YouTube exceptions
    "YouTubeServiceError",
    "VideoNotFoundError",
    "TranscriptNotAvailableError",
    "InvalidVideoIdError",
    "TranscriptAlreadyExistsError",
    # YouTube Data API (playlist sync) exceptions
    "YouTubeDataServiceError",
    "QuotaExceededError",
    "PermanentAPIError",
    # Agent exceptions
    "AgentServiceError",
    "AgentNotAvailableError",
    "SessionNotFoundError",
    "TranscriptNotFoundError",
    "IndexingError",
    "QueryExecutionError",
    # Cross-chat exceptions
    "CrossChatSessionNotFoundError",
    "CrossChatValidationError",
    # Document exceptions
    "DocumentServiceError",
    "DocumentNotFoundError",
    "DocumentIndexingError",
    "MaxDocumentsExceededError",
    "UnsupportedFileTypeError",
    "FileTooLargeError",
    # Watch history exceptions
    "WatchHistoryServiceError",
    "InvalidTakeoutFileError",
    "TakeoutFileTooLargeError",
    # Auth exceptions
    "AuthenticationError",
    "TokenError",
    "UserExistsError",
    "InvalidInvitationError",
    "InvitationExistsError",
    "InvitationLimitError",
    "InvitationNotFoundError",
    # Google auth exceptions
    "GoogleAuthServiceError",
    "GoogleAuthStateError",
    "GoogleCredentialNotFoundError",
    "GoogleTokenRefreshError",
    # Plan apply exceptions
    "PlanApplyError",
    "PlanNotFoundError",
    "apply_plan",
    # Factory functions
    "get_youtube_service",
    "get_transcript_service",
    "get_agent_service",
    "get_cross_chat_service",
    "get_settings_service",
    "get_system_settings_service",
    "get_auth_service",
    "get_user_service",
    "get_invitation_service",
    "get_document_service",
    "get_google_auth_service",
    "get_playlist_sync_service",
    "get_playlist_planning_service",
    "get_quota_service",
    "get_daily_quota_status",
    "get_watch_history_service",
]


def get_youtube_service() -> YouTubeService:
    """Factory function for dependency injection."""
    return YouTubeService()


def get_transcript_service(db: Session) -> TranscriptService:
    """Factory function for TranscriptService dependency injection."""
    repository = TranscriptRepository(db)
    youtube_service = YouTubeService()
    return TranscriptService(repository, youtube_service)


def get_agent_service(db: Session) -> AgentService:
    """Factory function for AgentService dependency injection."""
    repository = TranscriptRepository(db)
    session_repository = SessionRepository(db)
    document_service = get_document_service(db)
    return AgentService(
        repository,
        session_repository=session_repository,
        document_service=document_service,
    )


def get_cross_chat_service(db: Session) -> CrossChatService:
    """Factory function for CrossChatService dependency injection."""
    cross_chat_repository = CrossChatRepository(db)
    session_repository = SessionRepository(db)
    transcript_repository = TranscriptRepository(db)
    return CrossChatService(
        cross_chat_repository=cross_chat_repository,
        session_repository=session_repository,
        transcript_repository=transcript_repository,
    )


def get_document_service(db: Session) -> DocumentService:
    """Factory function for DocumentService dependency injection."""
    repository = DocumentRepository(db)
    return DocumentService(repository)
