"""Compatibility tests for the anthropic SDK, run without the network.

Like the openai compatibility tests, these keep the real SDK in the loop and swap
only the HTTP transport for an in-memory fake, so a new anthropic release that
renames an argument, moves an exception or changes its HTTP client shows up here.
"""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import anthropic
import httpx2
import pytest

from src.services.settings_service import SettingsService

MESSAGE_BODY: dict[str, Any] = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5",
    "content": [{"type": "text", "text": "hi"}],
    "stop_reason": "max_tokens",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}

# Kept before any patching, so the fake factory below can still build a real client.
REAL_ANTHROPIC = anthropic.Anthropic


def _anthropic_client(
    handler: Callable[[httpx2.Request], httpx2.Response], **kwargs: Any
) -> anthropic.Anthropic:
    """Build a real Anthropic client whose HTTP calls go to ``handler``."""
    kwargs.setdefault("api_key", "sk-ant-test")
    kwargs["max_retries"] = 0
    return REAL_ANTHROPIC(
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        **kwargs,
    )


def _patch_anthropic(handler: Callable[[httpx2.Request], httpx2.Response]) -> Any:
    """Patch ``anthropic.Anthropic`` so code that builds its own client gets the fake transport."""
    return patch(
        "anthropic.Anthropic", side_effect=lambda **kw: _anthropic_client(handler, **kw)
    )


class TestAnthropicKeyValidation:
    """The settings API-key check against the real SDK and its exception classes."""

    @pytest.fixture
    def service(self) -> SettingsService:
        """Create a SettingsService with a mocked repository."""
        return SettingsService(repository=MagicMock())

    def test_valid_key(self, service: SettingsService) -> None:
        """A successful one-token message means the key is valid."""
        seen: dict[str, Any] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.read())
            return httpx2.Response(200, json=MESSAGE_BODY)

        with _patch_anthropic(handler):
            assert service._validate_anthropic_key("sk-ant-test") == (True, None)
        assert seen["path"] == "/v1/messages"
        assert seen["body"]["model"] == "claude-sonnet-4-5"
        assert seen["body"]["max_tokens"] == 1
        assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]

    def test_invalid_key(self, service: SettingsService) -> None:
        """A 401 response is reported as an invalid key."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                401,
                json={
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "bad key"},
                },
            )

        with _patch_anthropic(handler):
            assert service._validate_anthropic_key("sk-ant-test") == (
                False,
                "Invalid API key",
            )

    def test_connection_error(self, service: SettingsService) -> None:
        """A network failure is reported as a connection problem."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("offline", request=request)

        with _patch_anthropic(handler):
            assert service._validate_anthropic_key("sk-ant-test") == (
                False,
                "Could not connect to Anthropic API",
            )


class TestAgnoClaude:
    """The agent model path: agno builds the anthropic client with the SDK's own HTTP client."""

    def test_message_through_agno_client_params(self) -> None:
        """agno's client settings work with the SDK, and it no longer injects an HTTP client."""
        from agno.models.anthropic import Claude

        client_kwargs: dict[str, Any] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json=MESSAGE_BODY)

        def fake_client(**kwargs: Any) -> anthropic.Anthropic:
            client_kwargs.update(kwargs)
            return _anthropic_client(handler, **kwargs)

        model = Claude(id="claude-sonnet-4-5", api_key="sk-ant-test")
        with patch("agno.models.anthropic.claude.AnthropicClient", side_effect=fake_client):
            client = model.get_client()

        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )

        assert "http_client" not in client_kwargs
        assert message.content[0].text == "hi"

    def test_default_client_uses_httpx2(self) -> None:
        """Without the patch, the client agno builds sends requests through httpx2."""
        from agno.models.anthropic import Claude

        client = Claude(id="claude-sonnet-4-5", api_key="sk-ant-test").get_client()

        assert isinstance(client._client, httpx2.Client)
