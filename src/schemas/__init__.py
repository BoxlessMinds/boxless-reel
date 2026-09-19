# Pydantic schemas
from src.schemas.agent import (
    CitationResponse,
    CreateSessionRequest,
    MessageResponse,
    QueryRequest,
    QueryResponseSchema,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)
from src.schemas.auth import (
    AdminUserUpdateRequest,
    BulkInvitationRequest,
    BulkInvitationResponse,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
    InvitationValidateResponse,
    RegistrationModeResponse,
    RegistrationModeUpdateRequest,
    ValidateTokenRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from src.schemas.document import (
    DocumentListItem,
    DocumentListResponse,
    DocumentResponse,
    DocumentSummary,
    DocumentUploadResponse,
    SessionDocumentsResponse,
)
from src.schemas.google_auth import (
    GoogleAuthConnectResponse,
    GoogleAuthDisconnectResponse,
    GoogleOAuthStatusResponse,
)
from src.schemas.cross_chat import (
    CreateCrossChatSessionRequest,
    CrossChatCitationResponse,
    CrossChatMessageResponse,
    CrossChatQueryRequest,
    CrossChatQueryResponse,
    CrossChatSessionDetailResponse,
    CrossChatSessionListResponse,
    CrossChatSessionResponse,
    SessionSummary,
)
from src.schemas.plan import (
    ApplyPlanRequest,
    CreatePlanRequest,
    PlanOpResponse,
    PlanResponse,
    QuotaResponse,
)
from src.schemas.playlist import (
    PlaylistItemListResponse,
    PlaylistItemResponse,
    PlaylistListResponse,
    PlaylistResponse,
    SyncResponse,
)
from src.schemas.settings import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    ProviderModels,
    ValidateKeyRequest,
    ValidateKeyResponse,
)
from src.schemas.transcript import (
    TranscriptExtractRequest,
    TranscriptListItem,
    TranscriptListQuery,
    TranscriptListResponse,
    TranscriptResponse,
    TranscriptSegment,
)
from src.schemas.watch_history import (
    WatchHistoryImportListResponse,
    WatchHistoryImportResponse,
)

__all__ = [
    # Transcript schemas
    "TranscriptSegment",
    "TranscriptExtractRequest",
    "TranscriptResponse",
    "TranscriptListQuery",
    "TranscriptListItem",
    "TranscriptListResponse",
    # Agent schemas
    "CreateSessionRequest",
    "QueryRequest",
    "CitationResponse",
    "SessionResponse",
    "QueryResponseSchema",
    "MessageResponse",
    "SessionDetailResponse",
    "SessionListResponse",
    # Google auth schemas
    "GoogleAuthConnectResponse",
    "GoogleOAuthStatusResponse",
    "GoogleAuthDisconnectResponse",
    # Document schemas
    "DocumentResponse",
    "DocumentListItem",
    "DocumentListResponse",
    "SessionDocumentsResponse",
    "DocumentSummary",
    "DocumentUploadResponse",
    # Settings schemas
    "LLMSettingsResponse",
    "LLMSettingsUpdate",
    "ProviderModels",
    "ValidateKeyRequest",
    "ValidateKeyResponse",
    # Cross-chat schemas
    "CreateCrossChatSessionRequest",
    "CrossChatCitationResponse",
    "CrossChatMessageResponse",
    "CrossChatQueryRequest",
    "CrossChatQueryResponse",
    "CrossChatSessionDetailResponse",
    "CrossChatSessionListResponse",
    "CrossChatSessionResponse",
    "SessionSummary",
    # Auth schemas
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "RegisterRequest",
    "UserResponse",
    "UserUpdateRequest",
    "AdminUserUpdateRequest",
    "UserListResponse",
    "InvitationCreateRequest",
    "InvitationResponse",
    "InvitationListResponse",
    "InvitationValidateResponse",
    "ValidateTokenRequest",
    "BulkInvitationRequest",
    "BulkInvitationResponse",
    "RegistrationModeResponse",
    "RegistrationModeUpdateRequest",
    # Playlist schemas
    "PlaylistResponse",
    "PlaylistListResponse",
    "PlaylistItemResponse",
    "PlaylistItemListResponse",
    "SyncResponse",
    # Plan/apply engine schemas
    "PlanResponse",
    "PlanOpResponse",
    "ApplyPlanRequest",
    "CreatePlanRequest",
    "QuotaResponse",
    # Watch-history schemas
    "WatchHistoryImportResponse",
    "WatchHistoryImportListResponse",
]
