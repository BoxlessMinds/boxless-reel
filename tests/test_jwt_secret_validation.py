"""Tests for the JWT secret check that runs when the API starts."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

# Obviously fake values used only by these tests
VALID_SECRET = "test-only-not-a-real-secret-" + "0" * 36
PLACEHOLDER = "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32"
RANDOM_HEX_VALUE = "0123456789abcdef" * 4

REPO_ROOT = Path(__file__).resolve().parent.parent


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
            PLACEHOLDER + "x",
            "prefix-" + PLACEHOLDER + "-suffix",
            PLACEHOLDER.lower() + "-extra",
            "z" * 32,
            "z" * 64,
            "  " + "z" * 40 + "\t\n",
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
            "placeholder-with-suffix",
            "placeholder-inside-longer-value",
            "placeholder-lowercase-with-suffix",
            "one-character-32",
            "one-character-64",
            "one-character-padded",
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

    @pytest.mark.parametrize("secret", [VALID_SECRET, RANDOM_HEX_VALUE])
    def test_startup_succeeds_for_valid_secret(
        self, monkeypatch: pytest.MonkeyPatch, secret: str
    ) -> None:
        """A secret of 32 or more characters starts normally."""
        monkeypatch.setattr(settings, "jwt_secret_key", secret)

        start_app()


def import_app_in_new_process(secret: str) -> subprocess.CompletedProcess[str]:
    """Import the app in a separate Python process with the given JWT_SECRET_KEY.

    Importing the module runs no startup handlers, so this covers servers that
    load the app without calling its lifespan.
    """
    env = os.environ.copy()
    env["JWT_SECRET_KEY"] = secret
    return subprocess.run(
        [sys.executable, "-c", "import src.main"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


class TestJwtSecretCheckedOnImport:
    """The secret is checked when settings load, not only in the startup handler."""

    @pytest.mark.parametrize(
        "secret",
        [PLACEHOLDER + "x", "z" * 32, "short-secret"],
        ids=["placeholder-with-suffix", "one-character", "too-short"],
    )
    def test_import_refused_for_unusable_secret(self, secret: str) -> None:
        """Importing the app stops with the clear message and never shows the value."""
        result = import_app_in_new_process(secret)

        assert result.returncode != 0
        assert "JWT_SECRET_KEY" in result.stderr
        assert "openssl rand -hex 32" in result.stderr
        assert secret not in result.stderr
        assert secret not in result.stdout

    def test_import_succeeds_for_valid_secret(self) -> None:
        """A random 64-character hex secret imports normally."""
        result = import_app_in_new_process(RANDOM_HEX_VALUE)

        assert result.returncode == 0, result.stderr
