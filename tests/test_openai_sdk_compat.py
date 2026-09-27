"""Compatibility tests for the openai SDK, run without the network.

The other tests patch the ``OpenAI`` client away, so they would not notice if a
new openai release renamed an argument or changed a response type. These tests
keep the real SDK in the loop and swap only the HTTP transport for an in-memory
fake, so each request is built, sent and parsed exactly as it would be in
production.
"""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import httpx2
import openai
import pytest

from src.services.settings_service import SettingsService
from src.services.whisper_service import WhisperTranscriptionService

CHAT_COMPLETION_BODY: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hi"},
            "finish_reason": "length",
        }
    ],
}

# Kept before any patching, so the fake factory below can still build a real client.
REAL_OPENAI = openai.OpenAI


def _openai_client(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> openai.OpenAI:
    """Build a real OpenAI client whose HTTP calls go to ``handler``."""
    return REAL_OPENAI(
        api_key="sk-test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _patch_openai(handler: Callable[[httpx2.Request], httpx2.Response]) -> Any:
    """Patch ``openai.OpenAI`` so code that builds its own client gets the fake transport."""
    return patch("openai.OpenAI", side_effect=lambda **_: _openai_client(handler))


class TestWhisperTranscriptionCall:
    """The Whisper service's transcription request against the real SDK."""

    def test_verbose_json_request_and_response(self, tmp_path):
        """The service sends the expected fields and reads segments from the response."""
        seen: dict[str, Any] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            seen["path"] = request.url.path
            seen["body"] = request.read()
            return httpx2.Response(
                200,
                json={
                    "text": " Hello world. ",
                    "language": "english",
                    "duration": 2.0,
                    "segments": [
                        {
                            "id": 0,
                            "seek": 0,
                            "start": 0.0,
                            "end": 1.5,
                            "text": " Hello world. ",
                            "tokens": [],
                            "temperature": 0.0,
                            "avg_logprob": 0.0,
                            "compression_ratio": 1.0,
                            "no_speech_prob": 0.0,
                        }
                    ],
                },
            )

        audio = tmp_path / "clip.mp3"
        audio.write_bytes(b"fake audio")
        service = WhisperTranscriptionService(api_key="sk-test")
        service.client = _openai_client(handler)

        result = service._transcribe_audio(str(audio))

        assert seen["path"] == "/v1/audio/transcriptions"
        for field in (b'name="model"', b'name="file"', b"verbose_json", b"segment"):
            assert field in seen["body"]
        assert result["full_text"] == "Hello world."
        assert result["language"] == "english"
        assert result["segments"] == [
            {"text": "Hello world.", "start": 0.0, "duration": 1.5}
        ]


class TestOpenAIKeyValidation:
    """The settings API-key check against the real SDK and its exception classes."""

    @pytest.fixture
    def service(self) -> SettingsService:
        """Create a SettingsService with a mocked repository."""
        return SettingsService(repository=MagicMock())

    def test_valid_key(self, service):
        """A successful chat completion (with ``max_tokens``) means the key is valid."""
        seen: dict[str, Any] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            seen["body"] = json.loads(request.read())
            return httpx2.Response(200, json=CHAT_COMPLETION_BODY)

        with _patch_openai(handler):
            assert service._validate_openai_key("sk-test") == (True, None)
        assert seen["body"]["max_tokens"] == 1

    def test_invalid_key(self, service):
        """A 401 response is reported as an invalid key."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(401, json={"error": {"message": "bad key"}})

        with _patch_openai(handler):
            assert service._validate_openai_key("sk-test") == (False, "Invalid API key")

    def test_connection_error(self, service):
        """A network failure is reported as a connection problem."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("offline", request=request)

        with _patch_openai(handler):
            assert service._validate_openai_key("sk-test") == (
                False,
                "Could not connect to OpenAI API",
            )


class TestAgnoOpenAIChat:
    """The agent model path: agno builds the openai client with the SDK's own HTTP client."""

    def test_chat_completion_through_agno_client_params(self):
        """agno's client settings work with the SDK, and it no longer injects an HTTP client."""
        from agno.models.openai import OpenAIChat

        client_kwargs: dict[str, Any] = {}

        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json=CHAT_COMPLETION_BODY)

        def fake_client(**kwargs: Any) -> openai.OpenAI:
            client_kwargs.update(kwargs)
            kwargs["max_retries"] = 0
            return REAL_OPENAI(
                http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
                **kwargs,
            )

        model = OpenAIChat(id="gpt-4o-mini", api_key="sk-test")
        with patch("agno.models.openai.chat.OpenAIClient", side_effect=fake_client):
            client = model.get_client()

        completion = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
        )

        assert "http_client" not in client_kwargs
        assert completion.choices[0].message.content == "hi"

    def test_default_client_uses_httpx2(self):
        """Without the patch, the client agno builds sends requests through httpx2."""
        from agno.models.openai import OpenAIChat

        client = OpenAIChat(id="gpt-4o-mini", api_key="sk-test").get_client()

        assert isinstance(client._client, httpx2.Client)
