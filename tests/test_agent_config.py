"""Tests for agent configuration."""

import pytest

from src.agents.config import AgentConfig, AgentConfigurationError, get_agent_config


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    @pytest.fixture
    def config_with_anthropic(self) -> AgentConfig:
        """AgentConfig with only Anthropic key set."""
        return AgentConfig(
            openai_api_key=None,
            anthropic_api_key="sk-ant-test",
            default_llm_provider="anthropic",
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri="./data/lancedb",
            max_context_chunks=10,
            chunk_size=1000,
            chunk_overlap=200,
        )

    @pytest.fixture
    def config_with_openai(self) -> AgentConfig:
        """AgentConfig with only OpenAI key set."""
        return AgentConfig(
            openai_api_key="sk-test",
            anthropic_api_key=None,
            default_llm_provider="openai",
            default_model="gpt-4o",
            embedding_model="text-embedding-3-small",
            lancedb_uri="./data/lancedb",
            max_context_chunks=10,
            chunk_size=1000,
            chunk_overlap=200,
        )

    @pytest.fixture
    def config_with_both(self) -> AgentConfig:
        """AgentConfig with both API keys set."""
        return AgentConfig(
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
            default_llm_provider="anthropic",
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri="./data/lancedb",
            max_context_chunks=10,
            chunk_size=1000,
            chunk_overlap=200,
        )

    @pytest.fixture
    def config_disabled(self) -> AgentConfig:
        """AgentConfig with no API keys set."""
        return AgentConfig(
            openai_api_key=None,
            anthropic_api_key=None,
            default_llm_provider="anthropic",
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri="./data/lancedb",
            max_context_chunks=10,
            chunk_size=1000,
            chunk_overlap=200,
        )

    def test_is_enabled_with_anthropic_key(self, config_with_anthropic: AgentConfig):
        """Agent is enabled when Anthropic key is set."""
        assert config_with_anthropic.is_enabled is True

    def test_is_enabled_with_openai_key(self, config_with_openai: AgentConfig):
        """Agent is enabled when OpenAI key is set."""
        assert config_with_openai.is_enabled is True

    def test_is_enabled_with_both_keys(self, config_with_both: AgentConfig):
        """Agent is enabled when both keys are set."""
        assert config_with_both.is_enabled is True

    def test_is_enabled_without_keys(self, config_disabled: AgentConfig):
        """Agent is disabled when no keys are set."""
        assert config_disabled.is_enabled is False

    def test_available_providers_anthropic_only(
        self, config_with_anthropic: AgentConfig
    ):
        """Only Anthropic listed when only Anthropic key set."""
        assert config_with_anthropic.available_providers == ["anthropic"]

    def test_available_providers_openai_only(self, config_with_openai: AgentConfig):
        """Only OpenAI listed when only OpenAI key set."""
        assert config_with_openai.available_providers == ["openai"]

    def test_available_providers_both(self, config_with_both: AgentConfig):
        """Both providers listed when both keys set."""
        providers = config_with_both.available_providers
        assert "anthropic" in providers
        assert "openai" in providers

    def test_available_providers_none(self, config_disabled: AgentConfig):
        """Empty list when no keys set."""
        assert config_disabled.available_providers == []

    def test_validate_provider_default(self, config_with_anthropic: AgentConfig):
        """Uses default provider when none specified."""
        result = config_with_anthropic.validate_provider()
        assert result == "anthropic"

    def test_validate_provider_explicit(self, config_with_both: AgentConfig):
        """Uses explicitly requested provider when available."""
        result = config_with_both.validate_provider("openai")
        assert result == "openai"

    def test_validate_provider_fallback_to_openai(
        self, config_with_openai: AgentConfig
    ):
        """Falls back to OpenAI when Anthropic requested but not configured."""
        # Config has OpenAI only, but default provider is set to openai
        config = AgentConfig(
            openai_api_key="sk-test",
            anthropic_api_key=None,
            default_llm_provider="anthropic",  # Default is anthropic
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri="./data/lancedb",
            max_context_chunks=10,
            chunk_size=1000,
            chunk_overlap=200,
        )
        result = config.validate_provider("anthropic")
        assert result == "openai"

    def test_validate_provider_fallback_to_anthropic(
        self, config_with_anthropic: AgentConfig
    ):
        """Falls back to Anthropic when OpenAI requested but not configured."""
        result = config_with_anthropic.validate_provider("openai")
        assert result == "anthropic"

    def test_validate_provider_no_providers_configured(
        self, config_disabled: AgentConfig
    ):
        """Raises error when no providers configured."""
        with pytest.raises(AgentConfigurationError) as exc_info:
            config_disabled.validate_provider()
        assert "No LLM provider configured" in str(exc_info.value)

    def test_get_model_id_default(self, config_with_anthropic: AgentConfig):
        """Returns default model for default provider."""
        model_id = config_with_anthropic.get_model_id()
        assert model_id == "claude-sonnet-4-5"

    def test_get_model_id_explicit_same_provider(self, config_with_both: AgentConfig):
        """Returns default model when requesting default provider explicitly."""
        model_id = config_with_both.get_model_id("anthropic")
        assert model_id == "claude-sonnet-4-5"

    def test_get_model_id_fallback_provider(self, config_with_both: AgentConfig):
        """Returns sensible default for non-default provider."""
        model_id = config_with_both.get_model_id("openai")
        assert model_id == "gpt-4o"


class TestGetAgentConfig:
    """Tests for get_agent_config factory function."""

    def test_returns_agent_config(self):
        """Factory returns AgentConfig instance."""
        # Clear cache to ensure fresh config
        get_agent_config.cache_clear()
        config = get_agent_config()
        assert isinstance(config, AgentConfig)

    def test_caching(self):
        """Factory returns cached instance."""
        get_agent_config.cache_clear()
        config1 = get_agent_config()
        config2 = get_agent_config()
        assert config1 is config2

    def test_cache_clear(self):
        """Cache can be cleared for testing."""
        get_agent_config.cache_clear()
        config1 = get_agent_config()
        get_agent_config.cache_clear()
        config2 = get_agent_config()
        # New instances after cache clear (but equal values)
        assert config1 == config2


class TestSettingsValidation:
    """Tests for Settings class agent-related validation."""

    def test_chunk_overlap_less_than_chunk_size_valid(self):
        """Valid when chunk_overlap < chunk_size."""
        from src.config import Settings

        # Should not raise
        s = Settings(chunk_size=500, chunk_overlap=100)
        assert s.chunk_overlap == 100
        assert s.chunk_size == 500

    def test_chunk_overlap_equal_to_chunk_size_invalid(self):
        """Invalid when chunk_overlap equals chunk_size."""
        from pydantic import ValidationError

        from src.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(chunk_size=500, chunk_overlap=500)
        assert "chunk_overlap" in str(exc_info.value)

    def test_chunk_overlap_greater_than_chunk_size_invalid(self):
        """Invalid when chunk_overlap > chunk_size."""
        from pydantic import ValidationError

        from src.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(chunk_size=500, chunk_overlap=600)
        assert "chunk_overlap" in str(exc_info.value)

    def test_agents_enabled_no_keys(self):
        """agents_enabled is False when no keys set."""
        from src.config import Settings

        s = Settings(openai_api_key=None, anthropic_api_key=None)
        assert s.agents_enabled is False

    def test_agents_enabled_with_anthropic_key(self):
        """agents_enabled is True when Anthropic key set."""
        from src.config import Settings

        s = Settings(anthropic_api_key="sk-ant-test")
        assert s.agents_enabled is True

    def test_agents_enabled_with_openai_key(self):
        """agents_enabled is True when OpenAI key set."""
        from src.config import Settings

        s = Settings(openai_api_key="sk-test")
        assert s.agents_enabled is True

    def test_default_provider_configured_anthropic(self):
        """default_provider_configured checks Anthropic key."""
        from src.config import Settings

        s = Settings(
            default_llm_provider="anthropic",
            anthropic_api_key="sk-ant-test",
        )
        assert s.default_provider_configured is True

    def test_default_provider_configured_openai(self):
        """default_provider_configured checks OpenAI key."""
        from src.config import Settings

        s = Settings(
            default_llm_provider="openai",
            openai_api_key="sk-test",
        )
        assert s.default_provider_configured is True

    def test_default_provider_not_configured(self):
        """default_provider_configured is False when key missing."""
        from src.config import Settings

        s = Settings(
            default_llm_provider="anthropic",
            anthropic_api_key=None,
        )
        assert s.default_provider_configured is False

    def test_max_context_chunks_bounds(self):
        """max_context_chunks respects bounds (1-50)."""
        from pydantic import ValidationError

        from src.config import Settings

        # Valid
        s = Settings(max_context_chunks=1)
        assert s.max_context_chunks == 1

        s = Settings(max_context_chunks=50)
        assert s.max_context_chunks == 50

        # Invalid - too low
        with pytest.raises(ValidationError):
            Settings(max_context_chunks=0)

        # Invalid - too high
        with pytest.raises(ValidationError):
            Settings(max_context_chunks=51)

    def test_chunk_size_bounds(self):
        """chunk_size respects bounds (100-5000)."""
        from pydantic import ValidationError

        from src.config import Settings

        # Valid
        s = Settings(chunk_size=100, chunk_overlap=50)
        assert s.chunk_size == 100

        s = Settings(chunk_size=5000, chunk_overlap=200)
        assert s.chunk_size == 5000

        # Invalid - too low
        with pytest.raises(ValidationError):
            Settings(chunk_size=99)

        # Invalid - too high
        with pytest.raises(ValidationError):
            Settings(chunk_size=5001)
