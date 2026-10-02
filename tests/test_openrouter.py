"""Tests for OpenRouter as a chat provider and as the embedding route."""

import pytest

from src.agents.config import OPENROUTER_BASE_URL, OPENROUTER_MAX_TOKENS, AgentConfig
from src.agents.knowledge.embeddings import (
    OpenRouterEmbeddings,
    create_embedding_function,
)


def make_config(**overrides) -> AgentConfig:
    """Build an AgentConfig with no keys set unless overridden."""
    values = {
        "openai_api_key": None,
        "anthropic_api_key": None,
        "openrouter_api_key": None,
        "default_llm_provider": "openrouter",
        "default_model": "anthropic/claude-sonnet-4.5",
        "embedding_model": "text-embedding-3-small",
        "lancedb_uri": "./data/lancedb",
        "max_context_chunks": 10,
        "chunk_size": 1000,
        "chunk_overlap": 200,
    }
    values.update(overrides)
    return AgentConfig(**values)


class TestOpenRouterProvider:
    """OpenRouter chat provider selection."""

    def test_openrouter_key_enables_agents(self):
        """An OpenRouter key on its own turns agent features on."""
        config = make_config(openrouter_api_key="sk-or-test")
        assert config.is_enabled is True
        assert config.available_providers == ["openrouter"]

    def test_default_openrouter_uses_default_model(self):
        """The default model is used when OpenRouter is the default provider."""
        config = make_config(openrouter_api_key="sk-or-test")
        assert config.validate_provider() == "openrouter"
        assert config.get_model_id() == "anthropic/claude-sonnet-4.5"

    def test_falls_back_to_openrouter(self):
        """A request for an unconfigured provider falls back to OpenRouter."""
        config = make_config(
            openrouter_api_key="sk-or-test", default_llm_provider="anthropic"
        )
        assert config.validate_provider("openai") == "openrouter"
        assert config.get_model_id("openai") == "anthropic/claude-sonnet-4.5"

    def test_create_model_returns_openrouter(self):
        """create_model builds an Agno OpenRouter model with the key and a higher token cap."""
        from agno.models.openrouter import OpenRouter

        config = make_config(openrouter_api_key="sk-or-test")
        model = config.create_model()

        assert isinstance(model, OpenRouter)
        assert model.id == "anthropic/claude-sonnet-4.5"
        assert model.api_key == "sk-or-test"
        assert model.max_tokens == OPENROUTER_MAX_TOKENS

    def test_settings_accept_openrouter(self):
        """DEFAULT_LLM_PROVIDER=openrouter is a valid setting."""
        from src.config import Settings

        s = Settings(default_llm_provider="openrouter", openrouter_api_key="sk-or-test")
        assert s.default_provider_configured is True
        assert s.agents_enabled is True


class TestEmbeddingConnection:
    """Choosing between OpenAI and OpenRouter for embeddings."""

    def test_openai_key_wins(self):
        """OpenAI is used directly whenever its key is set."""
        config = make_config(openai_api_key="sk-test", openrouter_api_key="sk-or-test")
        assert config.embedding_connection == ("text-embedding-3-small", "sk-test", None)

    def test_openrouter_used_without_openai_key(self):
        """Without an OpenAI key, OpenRouter serves the same model under its prefixed name."""
        config = make_config(openrouter_api_key="sk-or-test")
        assert config.embedding_connection == (
            "openai/text-embedding-3-small",
            "sk-or-test",
            OPENROUTER_BASE_URL,
        )

    def test_prefixed_model_left_alone(self):
        """A model name that already has a provider prefix isn't prefixed again."""
        config = make_config(
            openrouter_api_key="sk-or-test", embedding_model="openai/text-embedding-3-large"
        )
        assert config.embedding_connection[0] == "openai/text-embedding-3-large"

    def test_create_openrouter_embedding_function(self):
        """The OpenRouter embedding function points at OpenRouter with the right vector size."""
        config = make_config(openrouter_api_key="sk-or-test")
        func = create_embedding_function(config)

        assert isinstance(func, OpenRouterEmbeddings)
        assert func.name == "openai/text-embedding-3-small"
        assert func.base_url == OPENROUTER_BASE_URL
        assert func.api_key == "sk-or-test"
        assert func.ndims() == 1536

    def test_large_model_dimensions(self):
        """text-embedding-3-large has 3072 dimensions through OpenRouter too."""
        config = make_config(
            openrouter_api_key="sk-or-test", embedding_model="text-embedding-3-large"
        )
        assert create_embedding_function(config).ndims() == 3072

    def test_reopened_table_gets_the_key(self, tmp_path):
        """Opening a saved table in a fresh process supplies the OpenRouter key first.

        The table's saved embedding settings refer to the key by variable name,
        so a search straight after a restart needs that variable set.
        """
        from lancedb.embeddings import get_registry

        from src.agents.knowledge.embeddings import OPENROUTER_KEY_VARIABLE
        from src.agents.knowledge.transcript_knowledge import TranscriptKnowledgeBase

        config = make_config(openrouter_api_key="sk-or-test", lancedb_uri=str(tmp_path))
        TranscriptKnowledgeBase(config=config).table  # creates the table

        # Simulate a restart: the variable is gone
        get_registry()._variables.pop(OPENROUTER_KEY_VARIABLE, None)

        TranscriptKnowledgeBase(config=config).table  # opens the saved table
        assert get_registry().get_var(OPENROUTER_KEY_VARIABLE) == "sk-or-test"

    def test_unknown_model_rejected(self):
        """An embedding model with unknown dimensions gives a clear error."""
        func = OpenRouterEmbeddings.create(name="someone/mystery-embed")
        with pytest.raises(ValueError, match="Unknown embedding model"):
            func.ndims()
