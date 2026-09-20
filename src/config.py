"""Application configuration using pydantic-settings."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_MIN_LENGTH = 32
JWT_SECRET_PLACEHOLDER = "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    database_url: str = "sqlite:///./transcripts.db"
    log_level: str = "INFO"

    # Settings Encryption (for API keys stored in database)
    settings_encryption_key: str | None = Field(
        default=None,
        description="Fernet encryption key for securing API keys in database",
    )

    # JWT Authentication Configuration
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for signing JWT tokens (required, at least 32 characters; generate with: openssl rand -hex 32)",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm used for JWT encoding",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        description="Access token expiration time in minutes",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Refresh token expiration time in days",
    )

    # Registration Configuration
    require_invitation_code: bool = Field(
        default=True,
        description="Require invitation code for registration (can be overridden by admin via UI)",
    )

    # Invitation Configuration
    invitation_expire_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Invitation expiration time in days",
    )
    max_pending_invitations_per_user: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of pending invitations per user",
    )
    frontend_url: str = Field(
        default="http://localhost:8080",
        description="Frontend URL for constructing invitation links",
    )
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:8083"],
        description="Allowed CORS origins (set via ALLOWED_ORIGINS env var as JSON list or comma-separated)",
    )

    # Agent Configuration - API Keys (optional, agent features require at least one)
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for GPT models and embeddings",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key for Claude models",
    )

    # Agent Configuration - Model Selection
    default_llm_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic",
        description="Default LLM provider for agent queries",
    )
    default_model: str = Field(
        default="claude-sonnet-4-5",
        description="Default model ID for the chosen provider",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model for vector search",
    )

    # Whisper Fallback Configuration
    whisper_fallback_enabled: bool = Field(
        default=True,
        description="Enable Whisper API fallback when captions are unavailable",
    )
    whisper_model: str = Field(
        default="whisper-1",
        description="OpenAI Whisper model to use for audio transcription",
    )
    whisper_max_duration_seconds: int = Field(
        default=3600,
        ge=60,
        le=14400,
        description="Maximum video duration in seconds to attempt Whisper fallback (default 1 hour)",
    )
    whisper_audio_bitrate: str = Field(
        default="48k",
        description="Audio bitrate for mp3 compression (lower = smaller file, 48k keeps 1hr under 25MB)",
    )

    # Vector Database Configuration
    lancedb_uri: str = Field(
        default="./data/lancedb",
        description="Path to LanceDB storage directory",
    )

    # Agent Behavior Configuration
    max_context_chunks: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of transcript chunks to include in context",
    )
    chunk_size: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Target size for transcript text chunks (in characters)",
    )
    chunk_overlap: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Overlap between consecutive chunks (in characters)",
    )

    # Web Search Configuration (Tavily)
    tavily_api_key: str | None = Field(
        default=None,
        description="Tavily API key for web search",
    )
    web_search_enabled: bool = Field(
        default=True,
        description="Enable web search for agent queries",
    )
    web_search_max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum web search results to return",
    )

    # Google OAuth Configuration (YouTube playlist features)
    google_oauth_client_id: str | None = Field(
        default=None,
        description="Shared app-wide Google OAuth client ID",
    )
    google_oauth_client_secret: str | None = Field(
        default=None,
        description="Shared app-wide Google OAuth client secret",
    )
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8001/api/youtube-auth/callback",
        description="Must match a redirect URI registered in Google Cloud Console",
    )
    youtube_daily_quota_limit: int = Field(
        default=10000,
        ge=1,
        description="YouTube Data API v3 daily unit quota for the app's shared OAuth client",
    )
    youtube_default_apply_budget: int = Field(
        default=200,
        ge=1,
        description="Default units spent per apply() call when caller doesn't specify a budget",
    )
    watch_history_storage_path: str = Field(
        default="./data/watch-history",
        description="Path to store uploaded Takeout watch-history.json files",
    )

    # Document Upload Configuration
    documents_storage_path: str = Field(
        default="./data/documents",
        description="Path to document storage directory",
    )
    max_documents_per_session: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum documents allowed per session",
    )
    document_chunk_size: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Target size for document text chunks (in characters)",
    )
    document_chunk_overlap: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Overlap between consecutive document chunks (in characters)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info) -> int:
        """Ensure chunk overlap is less than chunk size."""
        chunk_size = info.data.get("chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({v}) must be less than chunk_size ({chunk_size})"
            )
        return v

    @property
    def agents_enabled(self) -> bool:
        """Check if at least one LLM provider is configured."""
        return bool(self.openai_api_key or self.anthropic_api_key)

    @property
    def youtube_enabled(self) -> bool:
        """Check if Google OAuth is configured for YouTube features."""
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    @property
    def default_provider_configured(self) -> bool:
        """Check if the default provider has an API key configured."""
        if self.default_llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return bool(self.openai_api_key)


def validate_jwt_secret(secret: str) -> None:
    """
    Check that the JWT secret is set to a usable value.

    Args:
        secret: The configured JWT_SECRET_KEY value

    Raises:
        ValueError: If the secret is empty, the example placeholder, or shorter
            than JWT_SECRET_MIN_LENGTH characters (surrounding whitespace is ignored).
            The message never includes the secret itself.
    """
    trimmed = secret.strip()
    if (
        len(trimmed) < JWT_SECRET_MIN_LENGTH
        or trimmed.upper() == JWT_SECRET_PLACEHOLDER
    ):
        raise ValueError(
            f"JWT_SECRET_KEY must be set to a value of at least {JWT_SECRET_MIN_LENGTH} "
            "characters. Generate one with either of these commands:\n"
            "  openssl rand -hex 32\n"
            '  uv run python -c "import secrets; print(secrets.token_hex(32))"\n'
            "Then set JWT_SECRET_KEY to the result in your .env file "
            "(.env.docker when using Docker)."
        )


settings = Settings()
