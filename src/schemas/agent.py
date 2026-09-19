"""Pydantic schemas for agent API request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreateSessionRequest(BaseModel):
    """Request body for creating a new query session."""

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


class QueryRequest(BaseModel):
    """Request body for querying a transcript."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask about the transcript",
    )


class CitationResponse(BaseModel):
    """A citation from transcript, document, or web source."""

    text: str = Field(description="The quoted text from the source")
    source_type: Literal["transcript", "document", "web"] = Field(
        default="transcript",
        description="Source type: 'transcript' for video content, 'document' for uploaded documents, 'web' for web search results"
    )

    # Transcript citation fields (null for other citation types)
    start_time: float | None = Field(
        default=None, description="Start timestamp in seconds (transcript only)"
    )
    end_time: float | None = Field(
        default=None, description="End timestamp in seconds (transcript only)"
    )
    timestamp_formatted: str | None = Field(
        default=None, description="Human-readable timestamp in MM:SS format (transcript only)"
    )

    # Document citation fields (null for other citation types)
    document_id: str | None = Field(
        default=None, description="Document UUID (document citations only)"
    )
    document_name: str | None = Field(
        default=None, description="Original filename (document citations only)"
    )
    page_number: int | None = Field(
        default=None, description="Page number in the document (document citations only)"
    )

    # Web citation fields (null for other citation types)
    url: str | None = Field(
        default=None, description="Source URL (web citations only)"
    )
    title: str | None = Field(
        default=None, description="Page title (web citations only)"
    )


class SessionResponse(BaseModel):
    """Session information response."""

    session_id: str = Field(description="Unique session identifier (UUID)")
    transcript_id: str = Field(description="ID of the transcript being queried")
    video_id: str = Field(description="YouTube video ID")
    video_title: str = Field(description="Video title")
    thumbnail_url: str | None = Field(default=None, description="Video thumbnail URL")
    model_provider: str = Field(description="LLM provider (anthropic/openai)")
    model_id: str = Field(description="Specific model ID being used")
    created_at: datetime = Field(description="When the session was created")
    last_activity: datetime = Field(description="Last activity timestamp")
    query_count: int = Field(description="Number of queries in this session")


class QueryResponseSchema(BaseModel):
    """Response from an agent query."""

    content: str = Field(description="The agent's response text")
    citations: list[CitationResponse] = Field(
        default_factory=list, description="Citations from transcript and/or web sources"
    )
    session_id: str = Field(description="Session ID for this query")
    model_used: str = Field(description="Model that generated the response")
    transcript_results_used: int = Field(
        description="Number of transcript chunks used in search"
    )
    web_results_used: int = Field(
        default=0, description="Number of web search results used"
    )
    created_at: datetime = Field(description="When the response was generated")


class MessageResponse(BaseModel):
    """A single message in conversation history."""

    role: str = Field(description="Message role: 'user' or 'assistant'")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(description="When the message was created")
    citations: list[CitationResponse] | None = Field(
        default=None, description="Citations (only for assistant messages)"
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate that role is a supported value."""
        if v not in ("user", "assistant"):
            raise ValueError("Role must be 'user' or 'assistant'.")
        return v


class SessionDetailResponse(SessionResponse):
    """Session with full conversation history."""

    messages: list[MessageResponse] = Field(
        default_factory=list, description="Conversation history"
    )


class SessionListResponse(BaseModel):
    """List of sessions response."""

    items: list[SessionResponse] = Field(description="List of sessions")
    total: int = Field(description="Total number of sessions")
