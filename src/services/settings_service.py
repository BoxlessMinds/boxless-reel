"""Service for managing application settings."""

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from src.agents.config import get_agent_config
from src.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


# Available models by provider
AVAILABLE_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-sonnet-4-5", "claude-opus-4-5"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
}


class SettingsService:
    """
    Service layer for settings operations.

    Implements priority order: Database -> Environment Variables -> Defaults
    """

    # Default values for all settings
    DEFAULTS: dict[str, str] = {
        "llm.default_provider": "anthropic",
        "llm.default_model": "claude-sonnet-4-5",
        "embedding.model": "text-embedding-3-small",
        "agent.max_context_chunks": "10",
        "agent.chunk_size": "1000",
        "agent.chunk_overlap": "200",
        "search.web_search_enabled": "true",
        "search.web_search_max_results": "5",
    }

    # Mapping from setting keys to environment variable names
    ENV_VAR_MAP: dict[str, str] = {
        "llm.anthropic_api_key": "ANTHROPIC_API_KEY",
        "llm.openai_api_key": "OPENAI_API_KEY",
        "llm.default_provider": "DEFAULT_LLM_PROVIDER",
        "llm.default_model": "DEFAULT_MODEL",
        "embedding.model": "EMBEDDING_MODEL",
        "agent.max_context_chunks": "MAX_CONTEXT_CHUNKS",
        "agent.chunk_size": "CHUNK_SIZE",
        "agent.chunk_overlap": "CHUNK_OVERLAP",
        "search.tavily_api_key": "TAVILY_API_KEY",
        "search.web_search_enabled": "WEB_SEARCH_ENABLED",
        "search.web_search_max_results": "WEB_SEARCH_MAX_RESULTS",
    }

    # Category mapping for settings
    CATEGORY_MAP: dict[str, str] = {
        "llm.anthropic_api_key": "llm",
        "llm.openai_api_key": "llm",
        "llm.default_provider": "llm",
        "llm.default_model": "llm",
        "embedding.model": "embedding",
        "agent.max_context_chunks": "agent",
        "agent.chunk_size": "agent",
        "agent.chunk_overlap": "agent",
        "search.tavily_api_key": "search",
        "search.web_search_enabled": "search",
        "search.web_search_max_results": "search",
    }

    def __init__(self, repository: SettingsRepository) -> None:
        """
        Initialize the settings service.

        Args:
            repository: Repository for database operations.
        """
        self.repository = repository

    def get_effective_value(self, key: str, user_id: str) -> str | None:
        """
        Get the effective value for a setting key.

        Priority: Database (user-specific) -> Environment Variable -> Default

        Args:
            key: The setting key (e.g., "llm.anthropic_api_key").
            user_id: UUID of the user to get settings for.

        Returns:
            The effective value, or None if not set anywhere.
        """
        # 1. Try database first (user-specific)
        db_value = self.repository.get(key, user_id=user_id)
        if db_value is not None:
            logger.debug("Using database value for %s (user=%s)", key, user_id)
            return db_value

        # 2. Try environment variable
        env_var = self.ENV_VAR_MAP.get(key)
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value:
                logger.debug("Using environment variable %s for %s", env_var, key)
                return env_value

        # 3. Return default
        default = self.DEFAULTS.get(key)
        if default:
            logger.debug("Using default value for %s", key)
        return default

    def get_all_effective_values(self, user_id: str) -> dict[str, str | None]:
        """
        Get all settings with their effective values for a user.

        Args:
            user_id: UUID of the user to get settings for.

        Returns:
            Dictionary of all setting keys to their effective values.
        """
        result: dict[str, str | None] = {}
        all_keys = set(self.DEFAULTS.keys()) | set(self.ENV_VAR_MAP.keys())
        for key in all_keys:
            result[key] = self.get_effective_value(key, user_id)
        return result

    def is_api_key_configured(self, provider: str, user_id: str) -> bool:
        """
        Check if an API key is configured for a provider.

        Args:
            provider: Provider name ("anthropic", "openai", or "tavily").
            user_id: UUID of the user to check for.

        Returns:
            True if the API key is configured (in DB or env var).
        """
        # Handle Tavily separately as it's a search provider
        if provider == "tavily":
            key = "search.tavily_api_key"
        else:
            key = f"llm.{provider}_api_key"
        value = self.get_effective_value(key, user_id)
        return bool(value)

    def get_available_providers(self, user_id: str) -> list[str]:
        """
        Get list of providers with configured API keys for a user.

        Args:
            user_id: UUID of the user to check for.

        Returns:
            List of provider names that have API keys configured.
        """
        providers = []
        for provider in ["anthropic", "openai"]:
            if self.is_api_key_configured(provider, user_id):
                providers.append(provider)
        return providers

    def update_setting(self, key: str, value: str, user_id: str) -> None:
        """
        Update a single setting for a user.

        Args:
            key: The setting key.
            value: The new value.
            user_id: UUID of the user to update settings for.
        """
        category = self.CATEGORY_MAP.get(key, "general")
        self.repository.set(key, value, user_id=user_id, category=category)
        logger.info("Updated setting: %s (user=%s)", key, user_id)

        # Clear agent config cache to pick up new settings
        self._invalidate_agent_config()

    def update_settings(self, settings: dict[str, Any], user_id: str) -> None:
        """
        Update multiple settings at once for a user.

        Args:
            settings: Dictionary of key-value pairs to update.
                     None values are ignored, empty strings clear the setting.
            user_id: UUID of the user to update settings for.
        """
        for key, value in settings.items():
            if value is None:
                continue  # None means "don't update"

            # Map schema field names to setting keys
            key_mapping = {
                "anthropic_api_key": "llm.anthropic_api_key",
                "openai_api_key": "llm.openai_api_key",
                "default_provider": "llm.default_provider",
                "default_model": "llm.default_model",
                "embedding_model": "embedding.model",
                "max_context_chunks": "agent.max_context_chunks",
                "chunk_size": "agent.chunk_size",
                "chunk_overlap": "agent.chunk_overlap",
                "tavily_api_key": "search.tavily_api_key",
                "web_search_enabled": "search.web_search_enabled",
                "web_search_max_results": "search.web_search_max_results",
            }

            setting_key = key_mapping.get(key)
            if setting_key:
                # Convert non-string values to strings
                if isinstance(value, bool):
                    str_value = str(value).lower()
                elif not isinstance(value, str):
                    str_value = str(value)
                else:
                    str_value = value
                category = self.CATEGORY_MAP.get(setting_key, "general")
                self.repository.set(setting_key, str_value, user_id=user_id, category=category)
                logger.debug("Updated setting: %s (user=%s)", setting_key, user_id)

        # Clear agent config cache to pick up new settings
        self._invalidate_agent_config()
        logger.info("Updated %d settings (user=%s)", len([v for v in settings.values() if v is not None]), user_id)

    def validate_api_key(self, provider: str, api_key: str) -> tuple[bool, str | None]:
        """
        Validate an API key by making a minimal API call.

        Args:
            provider: Provider name ("anthropic", "openai", or "tavily").
            api_key: The API key to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not api_key:
            return False, "API key cannot be empty"

        try:
            if provider == "anthropic":
                return self._validate_anthropic_key(api_key)
            elif provider == "openai":
                return self._validate_openai_key(api_key)
            elif provider == "tavily":
                return self._validate_tavily_key(api_key)
            else:
                return False, f"Unknown provider: {provider}"
        except Exception as e:
            logger.error("Error validating %s API key: %s", provider, e)
            return False, str(e)

    def _validate_anthropic_key(self, api_key: str) -> tuple[bool, str | None]:
        """Validate an Anthropic API key."""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            # Make a minimal request to validate the key
            client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True, None
        except anthropic.AuthenticationError:
            return False, "Invalid API key"
        except anthropic.APIConnectionError:
            return False, "Could not connect to Anthropic API"
        except Exception as e:
            return False, f"Validation failed: {str(e)}"

    def _validate_openai_key(self, api_key: str) -> tuple[bool, str | None]:
        """Validate an OpenAI API key."""
        try:
            import openai

            client = openai.OpenAI(api_key=api_key)
            # Make a minimal request to validate the key
            client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True, None
        except openai.AuthenticationError:
            return False, "Invalid API key"
        except openai.APIConnectionError:
            return False, "Could not connect to OpenAI API"
        except Exception as e:
            return False, f"Validation failed: {str(e)}"

    def _validate_tavily_key(self, api_key: str) -> tuple[bool, str | None]:
        """Validate a Tavily API key."""
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=api_key)
            # Make a minimal request to validate the key
            client.search("test", max_results=1)
            return True, None
        except Exception as e:
            error_msg = str(e).lower()
            if "invalid" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
                return False, "Invalid API key"
            if "connection" in error_msg:
                return False, "Could not connect to Tavily API"
            return False, f"Validation failed: {str(e)}"

    def _invalidate_agent_config(self) -> None:
        """Clear the agent config cache to pick up new settings."""
        get_agent_config.cache_clear()
        logger.debug("Agent config cache cleared")

    def get_settings_response_data(self, user_id: str) -> dict[str, Any]:
        """
        Get all settings formatted for API response for a user.

        Args:
            user_id: UUID of the user to get settings for.

        Returns:
            Dictionary with settings data for LLMSettingsResponse schema.
        """
        values = self.get_all_effective_values(user_id)

        return {
            "anthropic_api_key_configured": self.is_api_key_configured("anthropic", user_id),
            "openai_api_key_configured": self.is_api_key_configured("openai", user_id),
            "default_provider": values.get("llm.default_provider", "anthropic"),
            "default_model": values.get("llm.default_model", "claude-sonnet-4-5"),
            "available_providers": self.get_available_providers(user_id),
            "available_models": [
                {"provider": provider, "models": models}
                for provider, models in AVAILABLE_MODELS.items()
            ],
            "embedding_model": values.get("embedding.model", "text-embedding-3-small"),
            "max_context_chunks": int(values.get("agent.max_context_chunks", "10")),
            "chunk_size": int(values.get("agent.chunk_size", "1000")),
            "chunk_overlap": int(values.get("agent.chunk_overlap", "200")),
            # Web Search
            "tavily_api_key_configured": self.is_api_key_configured("tavily", user_id),
            "web_search_enabled": values.get("search.web_search_enabled", "true") == "true",
            "web_search_max_results": int(values.get("search.web_search_max_results", "5")),
        }


def get_settings_service(db: Session) -> SettingsService:
    """
    Factory function for SettingsService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured SettingsService instance.
    """
    from src.repositories import get_settings_repository

    repository = get_settings_repository(db)
    return SettingsService(repository)
