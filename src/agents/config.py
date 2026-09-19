"""Agent-specific configuration and utilities."""

import logging
from dataclasses import dataclass
from functools import lru_cache

from src.config import settings

logger = logging.getLogger(__name__)


class AgentConfigurationError(Exception):
    """Raised when agent configuration is invalid or incomplete."""

    pass


@dataclass(frozen=True)
class AgentConfig:
    """
    Agent configuration container.

    Provides a clean interface to agent-related settings with
    validation and helper methods for creating Agno components.
    """

    # API Keys
    openai_api_key: str | None
    anthropic_api_key: str | None

    # Model Configuration
    default_llm_provider: str
    default_model: str
    embedding_model: str

    # Vector DB
    lancedb_uri: str

    # Chunking Configuration
    max_context_chunks: int
    chunk_size: int
    chunk_overlap: int

    # Web Search Configuration
    tavily_api_key: str | None = None
    web_search_enabled: bool = True
    web_search_max_results: int = 5

    @property
    def is_enabled(self) -> bool:
        """Check if agent features are enabled (at least one API key set)."""
        return bool(self.openai_api_key or self.anthropic_api_key)

    @property
    def available_providers(self) -> list[str]:
        """List of providers with configured API keys."""
        providers = []
        if self.anthropic_api_key:
            providers.append("anthropic")
        if self.openai_api_key:
            providers.append("openai")
        return providers

    @property
    def is_web_search_available(self) -> bool:
        """Check if web search is available (Tavily API key set and enabled)."""
        return bool(self.tavily_api_key) and self.web_search_enabled

    def validate_provider(self, provider: str | None = None) -> str:
        """
        Validate and return the provider to use.

        Args:
            provider: Requested provider, or None to use default.

        Returns:
            The validated provider name.

        Raises:
            AgentConfigurationError: If provider is not available.
        """
        target_provider = provider or self.default_llm_provider

        if target_provider == "anthropic" and not self.anthropic_api_key:
            if self.openai_api_key:
                logger.warning(
                    "Anthropic requested but not configured, falling back to OpenAI"
                )
                return "openai"
            raise AgentConfigurationError(
                "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

        if target_provider == "openai" and not self.openai_api_key:
            if self.anthropic_api_key:
                logger.warning(
                    "OpenAI requested but not configured, falling back to Anthropic"
                )
                return "anthropic"
            raise AgentConfigurationError(
                "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

        return target_provider

    def get_model_id(self, provider: str | None = None) -> str:
        """
        Get the model ID for the specified or default provider.

        Args:
            provider: Target provider or None for default.

        Returns:
            Model ID string appropriate for the provider.
        """
        validated_provider = self.validate_provider(provider)

        # If using default provider, return default model
        if validated_provider == self.default_llm_provider:
            return self.default_model

        # Otherwise return sensible defaults for fallback providers
        if validated_provider == "anthropic":
            return "claude-sonnet-4-5"
        return "gpt-4o"

    def create_model(self, provider: str | None = None):
        """
        Create an Agno model instance for the specified provider.

        Args:
            provider: Target provider or None for default.

        Returns:
            Configured Agno model (Claude or OpenAIChat).

        Raises:
            AgentConfigurationError: If provider is not available.
            ImportError: If required provider package is not installed.
        """
        validated_provider = self.validate_provider(provider)
        model_id = self.get_model_id(provider)

        if validated_provider == "anthropic":
            try:
                from agno.models.anthropic import Claude

                return Claude(id=model_id)
            except ImportError as e:
                raise AgentConfigurationError(
                    "Anthropic provider requires 'anthropic' package. "
                    "Install with: uv add anthropic"
                ) from e

        # OpenAI
        try:
            from agno.models.openai import OpenAIChat

            return OpenAIChat(id=model_id)
        except ImportError as e:
            raise AgentConfigurationError(
                "OpenAI provider requires 'openai' package. "
                "Install with: uv add openai"
            ) from e


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    """
    Get the agent configuration singleton.

    Returns:
        AgentConfig instance populated from application settings.

    Note:
        Results are cached. Call get_agent_config.cache_clear() if
        settings change (primarily useful in tests).
    """
    return AgentConfig(
        openai_api_key=settings.openai_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        default_llm_provider=settings.default_llm_provider,
        default_model=settings.default_model,
        embedding_model=settings.embedding_model,
        lancedb_uri=settings.lancedb_uri,
        max_context_chunks=settings.max_context_chunks,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        tavily_api_key=settings.tavily_api_key,
        web_search_enabled=settings.web_search_enabled,
        web_search_max_results=settings.web_search_max_results,
    )


def get_agent_config_for_user(user_settings: dict) -> AgentConfig:
    """
    Build AgentConfig merging user-specific DB settings over global defaults.

    Args:
        user_settings: Dictionary of user-specific settings from the database.

    Returns:
        AgentConfig with user overrides applied.
    """
    base = get_agent_config()
    return AgentConfig(
        openai_api_key=user_settings.get("openai_api_key") or base.openai_api_key,
        anthropic_api_key=user_settings.get("anthropic_api_key") or base.anthropic_api_key,
        default_llm_provider=user_settings.get("default_llm_provider", base.default_llm_provider),
        default_model=user_settings.get("default_model", base.default_model),
        embedding_model=base.embedding_model,
        lancedb_uri=base.lancedb_uri,
        max_context_chunks=base.max_context_chunks,
        chunk_size=base.chunk_size,
        chunk_overlap=base.chunk_overlap,
        tavily_api_key=user_settings.get("tavily_api_key") or base.tavily_api_key,
        web_search_enabled=user_settings.get("web_search_enabled", base.web_search_enabled),
        web_search_max_results=base.web_search_max_results,
    )
