"""Pydantic schemas for cross-chat API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateCrossChatSessionRequest(BaseModel):
    """Request body for creating a new cross-chat session."""

    session_ids: list[str] = Field(
        ...,
        min_length=2,
        description="List of agent session IDs to include in the cross-chat (minimum 2).",
    )
    model_provider: str | None = Field(
        default=None,
        description="LLM provider: 'anthropic' or 'openai'. Defaults to configured provider.",
    )

    @field_validator("model_provider")
    @classmethod
    def validate_model_provider(cls, v: str | None) -> str | None:
        """Validate that model_provider is a supported value."""
        if v is not None and v not in ("anthropic", "openai"):
            raise ValueError(
                "Invalid model provider. Must be 'anthropic' or 'openai'."
            )
        return v

    @field_validator("session_ids")
    @classmethod
    def validate_session_ids(cls, v: list[str]) -> list[str]:
        """Validate that session_ids contains at least 2 unique IDs."""
        unique_ids = list(dict.fromkeys(v))  # deduplicate preserving order
        if len(unique_ids) < 2:
            raise ValueError("At least 2 unique session IDs are required.")
        return unique_ids


class CrossChatQueryRequest(BaseModel):
    """Request body for querying a cross-chat session."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask across multiple transcripts",
    )


class SessionSummary(BaseModel):
    """Summary of a referenced agent session within a cross-chat."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str = Field(description="Agent session UUID")
    transcript_id: str = Field(description="Transcript UUID")
    video_id: str = Field(description="YouTube video ID")
    video_title: str = Field(description="Video title")
    thumbnail_url: str | None = Field(default=None, description="Video thumbnail URL")


class CrossChatSessionResponse(BaseModel):
    """Cross-chat session information response."""

    id: str = Field(description="Cross-chat session UUID")
    referenced_sessions: list[SessionSummary] = Field(
        description="Referenced agent sessions with video info"
    )
    model_provider: str = Field(description="LLM provider (anthropic/openai)")
    model_name: str = Field(description="Specific model ID being used")
    created_at: datetime = Field(description="When the session was created")
    last_activity: datetime = Field(description="Last activity timestamp")
    query_count: int = Field(description="Number of queries in this session")


class CrossChatCitationResponse(BaseModel):
    """A citation from a cross-chat query response."""

    text: str = Field(description="The quoted text from the source")
    source_type: str = Field(
        default="transcript",
        description="Source type: 'transcript' or 'web'",
    )
    start_time: float | None = Field(
        default=None, description="Start timestamp in seconds (transcript only)"
    )
    end_time: float | None = Field(
        default=None, description="End timestamp in seconds (transcript only)"
    )
    timestamp_formatted: str | None = Field(
        default=None, description="Human-readable timestamp MM:SS (transcript only)"
    )
    video_id: str | None = Field(
        default=None, description="YouTube video ID for the source transcript"
    )
    video_title: str | None = Field(
        default=None, description="Video title for the source transcript"
    )
    url: str | None = Field(
        default=None, description="Source URL (web citations only)"
    )
    title: str | None = Field(
        default=None, description="Page title (web citations only)"
    )


class CrossChatMessageResponse(BaseModel):
    """A single message in cross-chat conversation history."""

    role: str = Field(description="Message role: 'user' or 'assistant'")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(description="When the message was created")
    citations: list[CrossChatCitationResponse] | None = Field(
        default=None, description="Citations (only for assistant messages)"
    )


class CrossChatSessionDetailResponse(CrossChatSessionResponse):
    """Cross-chat session with full conversation history."""

    messages: list[CrossChatMessageResponse] = Field(
        default_factory=list, description="Conversation history"
    )


class CrossChatSessionListResponse(BaseModel):
    """List of cross-chat sessions response."""

    items: list[CrossChatSessionResponse] = Field(
        description="List of cross-chat sessions"
    )
    total: int = Field(description="Total number of cross-chat sessions")


class CrossChatQueryResponse(BaseModel):
    """Response from a cross-chat query."""

    content: str = Field(description="The agent's response text")
    citations: list[CrossChatCitationResponse] = Field(
        default_factory=list, description="Citations from transcripts"
    )
    session_id: str = Field(description="Cross-chat session ID")
    model_used: str = Field(description="Model that generated the response")
    search_results_used: int = Field(
        description="Number of search results used"
    )
    created_at: datetime = Field(description="When the response was generated")
