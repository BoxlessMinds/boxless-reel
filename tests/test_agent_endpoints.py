"""Tests for agent API endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.transcript import Transcript
from src.routers.agent import _get_agent_service
from src.services import (
    AgentNotAvailableError,
    IndexingError,
    QueryExecutionError,
    SessionNotFoundError,
    TranscriptNotFoundError,
)
from src.services.agent_service import QueryResponse, SessionInfo


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_session_info(
    transcript_id: str,
    video_id: str = "dQw4w9WgXcQ",
    video_title: str = "Test Video",
    thumbnail_url: str | None = None,
    model_provider: str = "anthropic",
) -> SessionInfo:
    """Create a mock SessionInfo for testing."""
    return SessionInfo(
        session_id="test-session-123",
        transcript_id=transcript_id,
        video_id=video_id,
        video_title=video_title,
        thumbnail_url=thumbnail_url,
        model_provider=model_provider,
        model_id="claude-sonnet-4-5",
        created_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc),
        query_count=0,
    )


def create_mock_query_response(session_id: str = "test-session-123") -> QueryResponse:
    """Create a mock QueryResponse for testing."""
    return QueryResponse(
        content="This is the agent's answer about the transcript.",
        citations=[
            {
                "text": "relevant quote from transcript",
                "start_time": 10.5,
                "end_time": 15.0,
                "timestamp_formatted": "00:10",
            }
        ],
        session_id=session_id,
        model_used="claude-sonnet-4-5",
        transcript_results_used=3,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_agent_service_for_endpoints():
    """
    Create a mock AgentService and override the dependency.

    Yields the mock so tests can configure its behavior.
    """
    mock_service = MagicMock()

    # Override the FastAPI dependency
    app.dependency_overrides[_get_agent_service] = lambda: mock_service

    yield mock_service

    # Clean up override after test
    if _get_agent_service in app.dependency_overrides:
        del app.dependency_overrides[_get_agent_service]


# =============================================================================
# TestCreateSessionEndpoint
# =============================================================================


class TestCreateSessionEndpoint:
    """Tests for POST /api/transcripts/{transcript_id}/sessions."""

    def test_create_session_success(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Creates session with default provider, returns 201."""
        mock_session = create_mock_session_info(str(existing_transcript.id))
        mock_agent_service_for_endpoints.create_session.return_value = mock_session

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/sessions",
            json={},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert data["transcript_id"] == str(existing_transcript.id)
        assert data["model_provider"] == "anthropic"
        assert data["query_count"] == 0

    def test_create_session_with_provider(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Creates session with explicit model_provider."""
        mock_session = create_mock_session_info(
            str(existing_transcript.id),
            model_provider="openai",
        )
        mock_session.model_id = "gpt-4o"
        mock_agent_service_for_endpoints.create_session.return_value = mock_session

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/sessions",
            json={"model_provider": "openai"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["model_provider"] == "openai"
        assert data["model_id"] == "gpt-4o"

    def test_create_session_transcript_not_found(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 404 when transcript doesn't exist."""
        mock_agent_service_for_endpoints.create_session.side_effect = TranscriptNotFoundError(
            "Transcript not-found-id not found"
        )

        response = client.post(
            "/api/transcripts/not-found-id/sessions",
            json={},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_session_agent_not_available(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 503 when no API keys configured."""
        mock_agent_service_for_endpoints.create_session.side_effect = AgentNotAvailableError(
            "Agent features require an LLM API key."
        )

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/sessions",
            json={},
        )

        assert response.status_code == 503
        assert "API key" in response.json()["detail"]

    def test_create_session_indexing_error(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 500 when indexing fails."""
        mock_agent_service_for_endpoints.create_session.side_effect = IndexingError(
            "Failed to index transcript"
        )

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/sessions",
            json={},
        )

        assert response.status_code == 500
        assert "index" in response.json()["detail"].lower()


# =============================================================================
# TestQueryTranscriptOneshotEndpoint
# =============================================================================


class TestQueryTranscriptOneshotEndpoint:
    """Tests for POST /api/transcripts/{transcript_id}/query."""

    def test_query_oneshot_success(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns answer with citations, status 200."""
        mock_response = create_mock_query_response(session_id="")
        mock_agent_service_for_endpoints.query_oneshot.return_value = mock_response

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": "What is the main topic?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["content"]) > 0
        assert data["session_id"] == ""
        assert len(data["citations"]) > 0
        assert data["model_used"] == "claude-sonnet-4-5"

    def test_query_oneshot_with_provider(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Uses query param model_provider."""
        mock_response = create_mock_query_response(session_id="")
        mock_response.model_used = "gpt-4o"
        mock_agent_service_for_endpoints.query_oneshot.return_value = mock_response

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query?model_provider=openai",
            json={"question": "What is discussed?"},
        )

        assert response.status_code == 200
        # Verify service was called with the provider
        mock_agent_service_for_endpoints.query_oneshot.assert_called_once()
        call_kwargs = mock_agent_service_for_endpoints.query_oneshot.call_args.kwargs
        assert call_kwargs.get("model_provider") == "openai"

    def test_query_oneshot_transcript_not_found(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 404 for missing transcript."""
        mock_agent_service_for_endpoints.query_oneshot.side_effect = TranscriptNotFoundError(
            "Transcript not-found not found"
        )

        response = client.post(
            "/api/transcripts/not-found/query",
            json={"question": "What is this about?"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_query_oneshot_agent_not_available(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 503 when no API keys."""
        mock_agent_service_for_endpoints.query_oneshot.side_effect = AgentNotAvailableError(
            "No LLM API key configured"
        )

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 503

    def test_query_oneshot_indexing_error(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 500 when indexing fails."""
        mock_agent_service_for_endpoints.query_oneshot.side_effect = IndexingError(
            "Failed to index"
        )

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 500

    def test_query_oneshot_execution_error(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 500 when query fails."""
        mock_agent_service_for_endpoints.query_oneshot.side_effect = QueryExecutionError(
            "LLM API failed"
        )

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 500

    def test_query_oneshot_empty_question(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 422 validation error for empty question."""
        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": ""},
        )

        assert response.status_code == 422

    def test_query_oneshot_question_too_long(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 422 for question exceeding 2000 characters."""
        long_question = "x" * 2001

        response = client.post(
            f"/api/transcripts/{existing_transcript.id}/query",
            json={"question": long_question},
        )

        assert response.status_code == 422


# =============================================================================
# TestListSessionsEndpoint
# =============================================================================


class TestListSessionsEndpoint:
    """Tests for GET /api/sessions."""

    def test_list_sessions_empty(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns empty list when no sessions."""
        mock_agent_service_for_endpoints.list_sessions.return_value = []

        response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_sessions_with_sessions(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns all active sessions."""
        session1 = create_mock_session_info(str(existing_transcript.id))
        session2 = SessionInfo(
            session_id="session-456",
            transcript_id=str(existing_transcript.id),
            video_id="abc123",
            video_title="Another Video",
            thumbnail_url=None,
            model_provider="openai",
            model_id="gpt-4o",
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            query_count=5,
        )
        mock_agent_service_for_endpoints.list_sessions.return_value = [session1, session2]

        response = client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["session_id"] == "test-session-123"
        assert data["items"][1]["session_id"] == "session-456"

    def test_list_sessions_filter_by_transcript(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Filters by transcript_id query param."""
        mock_session = create_mock_session_info(str(existing_transcript.id))
        mock_agent_service_for_endpoints.list_sessions.return_value = [mock_session]

        response = client.get(f"/api/sessions?transcript_id={existing_transcript.id}")

        assert response.status_code == 200
        # Verify filter was passed to service
        mock_agent_service_for_endpoints.list_sessions.assert_called_once()
        call_kwargs = mock_agent_service_for_endpoints.list_sessions.call_args.kwargs
        assert call_kwargs.get("transcript_id") == str(existing_transcript.id)


# =============================================================================
# TestGetSessionEndpoint
# =============================================================================


class TestGetSessionEndpoint:
    """Tests for GET /api/sessions/{session_id}."""

    def test_get_session_success(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns session with history, status 200."""
        mock_session = create_mock_session_info(str(existing_transcript.id))
        mock_agent_service_for_endpoints.get_session.return_value = mock_session
        mock_agent_service_for_endpoints.get_session_history.return_value = []

        response = client.get("/api/sessions/test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert data["messages"] == []

    def test_get_session_not_found(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 404 for missing session."""
        mock_agent_service_for_endpoints.get_session.side_effect = SessionNotFoundError(
            "Session not-found not found"
        )

        response = client.get("/api/sessions/not-found")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_session_with_messages(
        self,
        client: TestClient,
        existing_transcript: Transcript,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns session including message history."""
        mock_session = create_mock_session_info(str(existing_transcript.id))
        mock_session.query_count = 2
        mock_agent_service_for_endpoints.get_session.return_value = mock_session

        mock_history = [
            {
                "role": "user",
                "content": "What is this video about?",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "role": "assistant",
                "content": "This video discusses Python programming.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "citations": [
                    {
                        "text": "Python is a programming language",
                        "start_time": 5.0,
                        "timestamp_formatted": "00:05",
                    }
                ],
            },
        ]
        mock_agent_service_for_endpoints.get_session_history.return_value = mock_history

        response = client.get("/api/sessions/test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
        assert "citations" in data["messages"][1]


# =============================================================================
# TestQuerySessionEndpoint
# =============================================================================


class TestQuerySessionEndpoint:
    """Tests for POST /api/sessions/{session_id}/query."""

    def test_query_session_success(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns answer with session context."""
        mock_response = create_mock_query_response(session_id="test-session-123")
        mock_agent_service_for_endpoints.query.return_value = mock_response

        response = client.post(
            "/api/sessions/test-session-123/query",
            json={"question": "What is the main topic?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert len(data["content"]) > 0
        assert "citations" in data

    def test_query_session_not_found(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 404 for missing session."""
        mock_agent_service_for_endpoints.query.side_effect = SessionNotFoundError(
            "Session not-found not found"
        )

        response = client.post(
            "/api/sessions/not-found/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_query_session_execution_error(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 500 when query fails."""
        mock_agent_service_for_endpoints.query.side_effect = QueryExecutionError(
            "LLM API error"
        )

        response = client.post(
            "/api/sessions/test-session-123/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 500

    def test_query_session_empty_question(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 422 validation error for empty question."""
        response = client.post(
            "/api/sessions/test-session-123/query",
            json={"question": ""},
        )

        assert response.status_code == 422


# =============================================================================
# TestDeleteSessionEndpoint
# =============================================================================


class TestDeleteSessionEndpoint:
    """Tests for DELETE /api/sessions/{session_id}."""

    def test_delete_session_success(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns success message, status 200."""
        mock_agent_service_for_endpoints.delete_session.return_value = None

        response = client.delete("/api/sessions/test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower() or "success" in data["message"].lower()

    def test_delete_session_not_found(
        self,
        client: TestClient,
        mock_agent_service_for_endpoints: MagicMock,
    ):
        """Returns 404 for missing session."""
        mock_agent_service_for_endpoints.delete_session.side_effect = SessionNotFoundError(
            "Session not-found not found"
        )

        response = client.delete("/api/sessions/not-found")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
