"""Tests for the per-user settings priority chain.

The chain is: the user's saved value -> loaded configuration -> hardcoded default.
"Configuration" here means whatever pydantic-settings resolved, which covers both
a real process environment variable and a value written only in `.env`. The tests
set the `settings` fields directly, so they pass or fail the same way whatever the
developer's own `.env` or shell contains.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.config import Settings, settings
from src.models import User
from src.services.settings_service import SettingsService, get_settings_service


class TestConfiguredValueReachesTheEndpoint:
    """A value that only `.env` supplied must reach `GET /api/settings`."""

    def test_default_model_from_env_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`DEFAULT_MODEL` set only in `.env` is reported as the default model."""
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)
        monkeypatch.setattr(settings, "default_model", "gpt-4o-mini")

        response = client.get("/api/settings")

        assert response.status_code == 200
        assert response.json()["default_model"] == "gpt-4o-mini"

    def test_default_provider_and_embedding_model_from_env_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other string settings take the same path."""
        monkeypatch.delenv("DEFAULT_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
        monkeypatch.setattr(settings, "default_llm_provider", "openai")
        monkeypatch.setattr(settings, "embedding_model", "text-embedding-3-large")

        body = client.get("/api/settings").json()

        assert body["default_provider"] == "openai"
        assert body["embedding_model"] == "text-embedding-3-large"

    def test_model_name_keeps_its_case(
        self, test_db: Session, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only booleans are lower-cased; a model name comes through unchanged."""
        monkeypatch.setattr(settings, "default_model", "My-Custom-Model")
        service = get_settings_service(test_db)

        assert service.get_effective_value("llm.default_model", test_user.id) == "My-Custom-Model"


class TestNumbersAndBooleans:
    """The chain is string-typed, so int and bool fields must be converted."""

    def test_int_settings_from_env_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`CHUNK_SIZE` and friends set only in `.env` reach the response as numbers."""
        for var in ("CHUNK_SIZE", "MAX_CONTEXT_CHUNKS", "WEB_SEARCH_MAX_RESULTS"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(settings, "chunk_size", 2500)
        monkeypatch.setattr(settings, "max_context_chunks", 25)
        monkeypatch.setattr(settings, "web_search_max_results", 8)

        body = client.get("/api/settings").json()

        assert body["chunk_size"] == 2500
        assert body["max_context_chunks"] == 25
        assert body["web_search_max_results"] == 8

    def test_zero_is_a_real_value(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`CHUNK_OVERLAP=0` is kept, not mistaken for "not set" and replaced by 200."""
        monkeypatch.delenv("CHUNK_OVERLAP", raising=False)
        monkeypatch.setattr(settings, "chunk_overlap", 0)

        body = client.get("/api/settings").json()

        assert body["chunk_overlap"] == 0

    def test_web_search_disabled_in_env_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`WEB_SEARCH_ENABLED=false` turns web search off instead of falling back to on."""
        monkeypatch.delenv("WEB_SEARCH_ENABLED", raising=False)
        monkeypatch.setattr(settings, "web_search_enabled", False)

        body = client.get("/api/settings").json()

        assert body["web_search_enabled"] is False

    def test_web_search_enabled_in_env_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The same path reports True, so the value is read and not just defaulted."""
        monkeypatch.setattr(settings, "web_search_enabled", True)

        body = client.get("/api/settings").json()

        assert body["web_search_enabled"] is True

    def test_service_returns_strings(
        self, test_db: Session, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bool becomes "true"/"false" and an int becomes its digits."""
        monkeypatch.setattr(settings, "web_search_enabled", False)
        monkeypatch.setattr(settings, "chunk_size", 1500)
        service = get_settings_service(test_db)

        assert service.get_effective_value("search.web_search_enabled", test_user.id) == "false"
        assert service.get_effective_value("agent.chunk_size", test_user.id) == "1500"


class TestStoredValueWins:
    """A value the user saved through the settings endpoint beats the configured value."""

    def test_saved_model_beats_configured_model(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A saved default model wins over `DEFAULT_MODEL` in `.env`."""
        monkeypatch.setattr(settings, "default_model", "gpt-4o-mini")

        put_response = client.put("/api/settings", json={"default_model": "claude-opus-4-5"})
        assert put_response.status_code == 200

        response = client.get("/api/settings")

        assert response.status_code == 200
        assert response.json()["default_model"] == "claude-opus-4-5"

    def test_saved_values_beat_configured_int_and_bool(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Saved int and bool values win over the configured ones too."""
        monkeypatch.setattr(settings, "chunk_size", 2500)
        monkeypatch.setattr(settings, "web_search_enabled", False)

        put_response = client.put(
            "/api/settings", json={"chunk_size": 800, "web_search_enabled": True}
        )
        assert put_response.status_code == 200

        body = client.get("/api/settings").json()

        assert body["chunk_size"] == 800
        assert body["web_search_enabled"] is True


class TestApiKeyConfigured:
    """`is_api_key_configured` must see a key from `.env`, and only a real key."""

    def test_key_only_in_env_file_counts_as_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keys set only in `.env` are reported as configured."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-not-a-real-key")
        monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-not-a-real-key")

        body = client.get("/api/settings").json()

        assert body["anthropic_api_key_configured"] is True
        assert body["tavily_api_key_configured"] is True

    def test_unset_key_is_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key that is set nowhere must not be reported as configured.

        Guards against turning `None` into the non-empty string "None".
        """
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        monkeypatch.setattr(settings, "openai_api_key", None)
        monkeypatch.setattr(settings, "tavily_api_key", None)

        body = client.get("/api/settings").json()

        assert body["anthropic_api_key_configured"] is False
        assert body["openai_api_key_configured"] is False
        assert body["tavily_api_key_configured"] is False
        assert body["available_providers"] == []

    def test_empty_key_is_not_configured(
        self, test_db: Session, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`TAVILY_API_KEY=` (as `.env.example` ships it) means "not set"."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setattr(settings, "tavily_api_key", "")
        service = get_settings_service(test_db)

        assert service.is_api_key_configured("tavily", test_user.id) is False
        assert service.get_effective_value("search.tavily_api_key", test_user.id) is None


class TestFallback:
    """The defaults table stays as the last step and agrees with the configuration."""

    def test_defaults_agree_with_settings_field_defaults(self) -> None:
        """Every key in DEFAULTS has the same default as its Settings field.

        Read straight off the class so a developer's own `.env` cannot change
        the answer.
        """
        for key, default in SettingsService.DEFAULTS.items():
            field = SettingsService.SETTINGS_FIELD_MAP.get(key)
            if field is None:
                continue
            field_default = Settings.model_fields[field].default
            if isinstance(field_default, bool):
                expected = str(field_default).lower()
            else:
                expected = str(field_default)
            assert default == expected, key

    def test_every_mapped_field_exists_on_settings(self) -> None:
        """A typo in the field map would silently skip the configuration step."""
        for field in SettingsService.SETTINGS_FIELD_MAP.values():
            assert field in Settings.model_fields, field

    def test_all_settings_keys_are_listed(
        self, test_db: Session, test_user: User
    ) -> None:
        """`get_all_effective_values` still covers every mapped and defaulted key."""
        service = get_settings_service(test_db)

        keys = set(service.get_all_effective_values(test_user.id))

        assert keys == set(SettingsService.DEFAULTS) | set(SettingsService.SETTINGS_FIELD_MAP)
        assert len(keys) == 12

    def test_unmapped_key_falls_back_to_the_defaults_table(
        self, test_db: Session, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key with no configuration field is still answered by DEFAULTS."""
        monkeypatch.setitem(SettingsService.DEFAULTS, "agent.some_other_setting", "42")
        service = get_settings_service(test_db)

        assert service.get_effective_value("agent.some_other_setting", test_user.id) == "42"
