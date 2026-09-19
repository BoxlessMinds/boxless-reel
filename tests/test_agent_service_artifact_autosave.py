"""Tests for AgentService's artifact auto-save hook in query().

Uses hand-built mocks rather than the fixtures in test_agent_service.py,
since several of those fixtures are already out of sync with the current
AgentResponse/SessionInfo dataclasses (pre-existing, unrelated to this
feature) and would error during setup.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.agents import AgentResponse, Citation
from src.repositories import SessionRepository, TranscriptRepository
from src.services import AgentService, SessionInfo
from src.services.document_service import DocumentService

SESSION_ID = "session-1"
USER_ID = "user-1"

DIAGRAM_REPLY = "Here is a diagram:\n\n```mermaid\ngraph TD;\nA-->B;\n```\n"
PLAIN_REPLY = "Sure, the answer is 42."


def make_service(
    *,
    session_repository: MagicMock,
    document_service: MagicMock | None,
) -> AgentService:
    transcript_repository = MagicMock(spec=TranscriptRepository)
    service = AgentService(
        transcript_repository,
        session_repository=session_repository,
        document_service=document_service,
    )
    service._sessions[SESSION_ID] = SessionInfo(
        session_id=SESSION_ID,
        transcript_id="transcript-1",
        video_id="dQw4w9WgXcQ",
        video_title="Test Video",
        thumbnail_url=None,
        model_provider="anthropic",
        model_id="claude-sonnet-4-5",
    )

    mock_agent = MagicMock()
    mock_agent.query.return_value = AgentResponse(
        content=DIAGRAM_REPLY,
        citations=[Citation(text="cited text")],
        session_id=SESSION_ID,
        model_used="claude-sonnet-4-5",
        created_at=datetime.now(timezone.utc),
    )
    service._agents[SESSION_ID] = mock_agent
    return service


@pytest.fixture(autouse=True)
def _clear_registries():
    from src.services.agent_service import _agents_registry, _sessions_registry

    _sessions_registry.clear()
    _agents_registry.clear()
    yield
    _sessions_registry.clear()
    _agents_registry.clear()


@pytest.fixture
def mock_session_repository() -> MagicMock:
    repo = MagicMock(spec=SessionRepository)
    repo.get.return_value = MagicMock()  # ownership check passes

    def add_message(session_id, role, content, citations=None, tokens_used=None):
        message = MagicMock()
        message.id = f"msg-{role}"
        message.content = content
        return message

    repo.add_message.side_effect = add_message
    return repo


class TestArtifactAutoSaveOnQuery:
    def test_saves_promoted_artifact_from_assistant_reply(
        self, mock_session_repository: MagicMock
    ) -> None:
        document_service = MagicMock(spec=DocumentService)
        service = make_service(
            session_repository=mock_session_repository, document_service=document_service
        )

        service.query(SESSION_ID, USER_ID, "Show me a diagram")

        document_service.save_artifact_document.assert_called_once()
        call_kwargs = document_service.save_artifact_document.call_args.kwargs
        assert call_kwargs["artifact"].kind == "mermaid"
        assert call_kwargs["session_id"] == SESSION_ID
        assert call_kwargs["user_id"] == USER_ID
        assert call_kwargs["source_message_id"] == "msg-assistant"
        assert call_kwargs["source_block_index"] == 0

    def test_no_document_service_is_a_noop(self, mock_session_repository: MagicMock) -> None:
        service = make_service(session_repository=mock_session_repository, document_service=None)

        # Must not raise even though there's no document_service to save to.
        response = service.query(SESSION_ID, USER_ID, "Show me a diagram")
        assert response.content == DIAGRAM_REPLY

    def test_no_artifact_in_reply_skips_save(self, mock_session_repository: MagicMock) -> None:
        document_service = MagicMock(spec=DocumentService)
        service = make_service(
            session_repository=mock_session_repository, document_service=document_service
        )
        service._agents[SESSION_ID].query.return_value = AgentResponse(
            content=PLAIN_REPLY,
            citations=[],
            session_id=SESSION_ID,
            model_used="claude-sonnet-4-5",
            created_at=datetime.now(timezone.utc),
        )

        service.query(SESSION_ID, USER_ID, "What's the answer?")

        document_service.save_artifact_document.assert_not_called()

    def test_save_failure_does_not_fail_the_query(self, mock_session_repository: MagicMock) -> None:
        document_service = MagicMock(spec=DocumentService)
        document_service.save_artifact_document.side_effect = RuntimeError("disk full")
        service = make_service(
            session_repository=mock_session_repository, document_service=document_service
        )

        # Must return normally, not propagate the save failure.
        response = service.query(SESSION_ID, USER_ID, "Show me a diagram")
        assert response.content == DIAGRAM_REPLY
