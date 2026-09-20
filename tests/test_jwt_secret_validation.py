"""Tests for the JWT secret check that runs when the API starts."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

# Obviously fake values used only by these tests
VALID_SECRET = "test-only-not-a-real-secret-" + "0" * 36
PLACEHOLDER = "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32"


def start_app() -> None:
    """Run the app's startup and shutdown handlers once."""
    with patch("src.main.Base.metadata.create_all"):
        with TestClient(app):
            pass


class TestJwtSecretValidation:
    """The API must only start with a usable JWT_SECRET_KEY."""

    @pytest.mark.parametrize(
        "secret",
        [
            "",
            "   ",
            PLACEHOLDER,
            PLACEHOLDER.lower(),
            f"  {PLACEHOLDER}  ",
            "short-secret",
            "a" * 31,
            " " * 40,
            "a" * 30 + "  ",
        ],
        ids=[
            "empty",
            "blank",
            "placeholder",
            "placeholder-lowercase",
            "placeholder-padded",
            "too-short",
            "one-under-minimum",
            "only-spaces",
            "short-padded-with-spaces",
        ],
    )
    def test_startup_refused_for_unusable_secret(
        self, monkeypatch: pytest.MonkeyPatch, secret: str
    ) -> None:
        """Startup stops with a message that says how to generate a secret."""
        monkeypatch.setattr(settings, "jwt_secret_key", secret)

        with pytest.raises(RuntimeError) as exc_info:
            start_app()

        message = str(exc_info.value)
        assert "JWT_SECRET_KEY" in message
        assert "openssl rand -hex 32" in message
        assert "secrets.token_hex(32)" in message

    def test_error_message_does_not_contain_the_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The message never repeats the configured value."""
        secret = "too-short-but-unique-marker"
        monkeypatch.setattr(settings, "jwt_secret_key", secret)

        with pytest.raises(RuntimeError) as exc_info:
            start_app()

        assert secret not in str(exc_info.value)

    @pytest.mark.parametrize("secret", [VALID_SECRET, "b" * 32])
    def test_startup_succeeds_for_valid_secret(
        self, monkeypatch: pytest.MonkeyPatch, secret: str
    ) -> None:
        """A secret of 32 or more characters starts normally."""
        monkeypatch.setattr(settings, "jwt_secret_key", secret)

        start_app()
