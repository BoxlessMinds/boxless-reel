"""Tests for the registration-mode priority chain.

The chain is: database value -> loaded configuration -> hardcoded default.
"config" here means whatever pydantic-settings resolved, which covers both a
real process environment variable and a value written only in `.env`.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.config import Settings, settings
from src.services.system_settings_service import (
    DEFAULTS,
    SystemSettingsService,
    get_system_settings_service,
)

REGISTRATION_KEY = "registration.require_invitation"


class TestConfiguredValueReachesTheEndpoint:
    """A value that only `.env` supplied must reach the public endpoint."""

    def test_false_in_env_file_opens_registration(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`REQUIRE_INVITATION_CODE=false` in `.env` alone disables the invitation."""
        monkeypatch.setattr(settings, "require_invitation_code", False)

        response = client.get("/api/auth/registration-mode")

        assert response.status_code == 200
        assert response.json() == {"require_invitation": False}

    def test_true_in_env_file_keeps_registration_invite_only(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The same path reports True, so the value is read and not just defaulted."""
        monkeypatch.setattr(settings, "require_invitation_code", True)

        response = client.get("/api/auth/registration-mode")

        assert response.status_code == 200
        assert response.json() == {"require_invitation": True}

    def test_service_returns_a_lowercase_string_for_a_boolean_setting(
        self, test_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The chain is string-typed, so a bool must be normalised to "true"/"false"."""
        monkeypatch.setattr(settings, "require_invitation_code", False)
        service = get_system_settings_service(test_db)

        assert service.get_effective_value(REGISTRATION_KEY) == "false"


class TestStoredValueWins:
    """An admin-saved database value beats the configured value, both ways."""

    def test_stored_false_beats_configured_true(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Saving "open registration" wins over an invite-only configuration."""
        monkeypatch.setattr(settings, "require_invitation_code", True)

        put_response = admin_client.put(
            "/api/admin/settings/registration-mode",
            json={"require_invitation": False},
        )
        assert put_response.status_code == 200

        response = admin_client.get("/api/auth/registration-mode")

        assert response.status_code == 200
        assert response.json() == {"require_invitation": False}

    def test_stored_true_beats_configured_false(
        self, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Saving "invite only" wins over an open-registration configuration."""
        monkeypatch.setattr(settings, "require_invitation_code", False)

        put_response = admin_client.put(
            "/api/admin/settings/registration-mode",
            json={"require_invitation": True},
        )
        assert put_response.status_code == 200

        response = admin_client.get("/api/auth/registration-mode")

        assert response.status_code == 200
        assert response.json() == {"require_invitation": True}


class TestFallback:
    """With nothing stored and nothing configured, the safe default applies."""

    def test_unmapped_key_falls_back_to_the_defaults_table(
        self, test_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key with no configuration field is still answered by DEFAULTS."""
        monkeypatch.setitem(DEFAULTS, "registration.some_other_flag", "true")
        service = get_system_settings_service(test_db)

        assert service.get_effective_value("registration.some_other_flag") == "true"

    def test_unknown_key_resolves_to_none(self, test_db: Session) -> None:
        """A key in neither table has no value anywhere in the chain."""
        service = get_system_settings_service(test_db)

        assert service.get_effective_value("registration.does_not_exist") is None

    def test_shipped_default_keeps_registration_invite_only(self) -> None:
        """With nothing set anywhere the shipped default is still invite-required.

        Read straight off the class so a developer's own `.env` cannot change
        the answer, and check the service's fallback table agrees with it.
        """
        field_default = Settings.model_fields["require_invitation_code"].default

        assert field_default is True
        assert DEFAULTS[REGISTRATION_KEY] == "true"

    def test_is_invitation_required_reads_the_resolved_value(
        self, test_db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The negative match in is_invitation_required sees a real string."""
        service: SystemSettingsService = get_system_settings_service(test_db)

        monkeypatch.setattr(settings, "require_invitation_code", False)
        assert service.is_invitation_required() is False

        monkeypatch.setattr(settings, "require_invitation_code", True)
        assert service.is_invitation_required() is True
