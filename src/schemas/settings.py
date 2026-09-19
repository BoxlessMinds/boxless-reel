"""Pydantic schemas for settings API endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class ProviderModels(BaseModel):
    """Available models for a provider."""

    provider: Literal["anthropic", "openai"]
    models: list[str]


class LLMSettingsResponse(BaseModel):
    """Response schema for GET /api/settings."""

    # API Key status (never expose actual keys)
    anthropic_api_key_configured: bool = Field(
        description="Whether Anthropic API key is configured"
    )
    openai_api_key_configured: bool = Field(
        description="Whether OpenAI API key is configured"
    )

    # LLM Configuration
    default_provider: Literal["anthropic", "openai"] = Field(
        description="Default LLM provider for agent queries"
    )
    default_model: str = Field(
        description="Default model ID for the chosen provider"
    )
    available_providers: list[str] = Field(
        description="List of providers with configured API keys"
    )
    available_models: list[ProviderModels] = Field(
        description="Available models grouped by provider"
    )

    # Embedding Configuration
    embedding_model: str = Field(
        description="OpenAI embedding model for vector search"
    )

    # Agent Behavior
    max_context_chunks: int = Field(
        ge=1, le=50,
        description="Maximum transcript chunks to include in context"
    )
    chunk_size: int = Field(
        ge=100, le=5000,
        description="Target size for transcript text chunks (characters)"
    )
    chunk_overlap: int = Field(
        ge=0, le=500,
        description="Overlap between consecutive chunks (characters)"
    )

    # Web Search
    tavily_api_key_configured: bool = Field(
        default=False,
        description="Whether Tavily API key is configured"
    )
    web_search_enabled: bool = Field(
        default=True,
        description="Whether web search is enabled for agent queries"
    )
    web_search_max_results: int = Field(
        default=5,
        ge=1, le=10,
        description="Maximum web search results to return"
    )


class LLMSettingsUpdate(BaseModel):
    """Request schema for PUT /api/settings.

    All fields are optional. None means "don't update".
    Empty string for API keys means "clear the value".
    """

    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key. None = don't update, empty = clear"
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key. None = don't update, empty = clear"
    )
    default_provider: Literal["anthropic", "openai"] | None = Field(
        default=None,
        description="Default LLM provider"
    )
    default_model: str | None = Field(
        default=None,
        description="Default model ID"
    )
    embedding_model: str | None = Field(
        default=None,
        description="Embedding model for vector search"
    )
    max_context_chunks: int | None = Field(
        default=None,
        ge=1, le=50,
        description="Maximum transcript chunks in context"
    )
    chunk_size: int | None = Field(
        default=None,
        ge=100, le=5000,
        description="Target chunk size in characters"
    )
    chunk_overlap: int | None = Field(
        default=None,
        ge=0, le=500,
        description="Chunk overlap in characters"
    )

    # Web Search
    tavily_api_key: str | None = Field(
        default=None,
        description="Tavily API key. None = don't update, empty = clear"
    )
    web_search_enabled: bool | None = Field(
        default=None,
        description="Enable/disable web search for agent queries"
    )
    web_search_max_results: int | None = Field(
        default=None,
        ge=1, le=10,
        description="Maximum web search results to return"
    )


class ValidateKeyRequest(BaseModel):
    """Request schema for POST /api/settings/validate-key."""

    provider: Literal["anthropic", "openai", "tavily"] = Field(
        description="Provider to validate key for (anthropic, openai, or tavily)"
    )
    api_key: str = Field(
        min_length=1,
        description="API key to validate"
    )


class ValidateKeyResponse(BaseModel):
    """Response schema for POST /api/settings/validate-key."""

    valid: bool = Field(
        description="Whether the API key is valid"
    )
    error: str | None = Field(
        default=None,
        description="Error message if validation failed"
    )
