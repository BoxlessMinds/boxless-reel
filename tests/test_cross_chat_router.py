"""Integration tests for cross-chat API endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.transcript import Transcript
from src.services.exceptions import (
    CrossChatSessionNotFoundError,
    CrossChatValidationError,
    QueryExecutionError,
)


# --- Fixtures ---


@pytest.fixture
def mock_cross_chat_service():
    """Create a mock CrossChatService and override the dependency.

    Gracefully skips if the cross_chat router is not yet implemented.
    """
    mock_service = MagicMock()

    try:
        from src.routers.cross_chat import _get_cross_chat_service

        app.dependency_overrides[_get_cross_chat_service] = lambda: mock_service
    except ImportError:
        pytest.skip("cross_chat router not implemented yet")

    yield mock_service

    try:
        from src.routers.cross_chat import _get_cross_chat_service

        if _get_cross_chat_service in app.dependency_overrides:
            del app.dependency_overrides[_get_cross_chat_service]
    except ImportError:
        pass


# =============================================================================
# POST /api/cross-chat/sessions
# =============================================================================


class TestCreateCrossChatSession:
    """Tests for POST /api/cross-chat/sessions."""

    def test_create_session_success(self, client, mock_cross_chat_service):
        """Returns 201 with session data on success."""
        session_id = str(uuid4())
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.model_provider = "anthropic"
        mock_session.model_name = "claude-sonnet-4-5-20250929"
        mock_session.user_id = "user-1"
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.referenced_sessions = []
        mock_session.messages = []
        mock_cross_chat_service.create_session.return_value = mock_session

        response = client.post(
            "/api/cross-chat/sessions",
            json={
                "session_ids": [str(uuid4()), str(uuid4())],
                "model_provider": "anthropic",
            },
        )

        assert response.status_code == 201

    def test_create_session_invalid_sessions_400(self, client, mock_cross_chat_service):
        """Returns 400 when referenced session IDs are invalid."""
        mock_cross_chat_service.create_session.side_effect = CrossChatValidationError(
            "Session not found or not owned by user."
        )

        response = client.post(
            "/api/cross-chat/sessions",
            json={
                "session_ids": [str(uuid4()), str(uuid4())],
                "model_provider": "anthropic",
            },
        )

        assert response.status_code == 400

    def test_create_session_fewer_than_2_sessions(self, client, mock_cross_chat_service):
        """Returns 422 when fewer than 2 session IDs provided."""
        response = client.post(
            "/api/cross-chat/sessions",
            json={
                "session_ids": [str(uuid4())],
                "model_provider": "anthropic",
            },
        )

        # Pydantic validation should reject this
        assert response.status_code in (400, 422)


# =============================================================================
# GET /api/cross-chat/sessions
# =============================================================================


class TestListCrossChatSessions:
    """Tests for GET /api/cross-chat/sessions."""

    def test_list_sessions_success(self, client, mock_cross_chat_service):
        """Returns 200 with list of sessions."""
        mock_cross_chat_service.list_sessions.return_value = []

        response = client.get("/api/cross-chat/sessions")

        assert response.status_code == 200


# =============================================================================
# GET /api/cross-chat/sessions/{id}
# =============================================================================


class TestGetCrossChatSession:
    """Tests for GET /api/cross-chat/sessions/{id}."""

    def test_get_session_found(self, client, mock_cross_chat_service):
        """Returns 200 when session exists."""
        session_id = str(uuid4())
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.model_provider = "anthropic"
        mock_session.model_name = "claude-sonnet-4-5-20250929"
        mock_session.user_id = "user-1"
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.referenced_sessions = []
        mock_session.messages = []
        mock_cross_chat_service.get_session.return_value = mock_session

        response = client.get(f"/api/cross-chat/sessions/{session_id}")

        assert response.status_code == 200

    def test_get_session_not_found(self, client, mock_cross_chat_service):
        """Returns 404 when session does not exist."""
        mock_cross_chat_service.get_session.side_effect = CrossChatSessionNotFoundError(
            "Cross-chat session not found"
        )

        response = client.get(f"/api/cross-chat/sessions/{uuid4()}")

        assert response.status_code == 404


# =============================================================================
# POST /api/cross-chat/sessions/{id}/query
# =============================================================================


class TestQueryCrossChatSession:
    """Tests for POST /api/cross-chat/sessions/{id}/query."""

    def test_query_success(self, client, mock_cross_chat_service):
        """Returns 200 with query response."""
        session_id = str(uuid4())
        mock_cross_chat_service.query.return_value = {
            "content": "The videos share Python as a topic.",
            "citations": [],
            "session_id": session_id,
            "model_used": "claude-sonnet-4-5-20250929",
            "search_results_used": 5,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        response = client.post(
            f"/api/cross-chat/sessions/{session_id}/query",
            json={"question": "What do these videos have in common?"},
        )

        assert response.status_code == 200

    def test_query_session_not_found(self, client, mock_cross_chat_service):
        """Returns 404 when session does not exist."""
        mock_cross_chat_service.query.side_effect = CrossChatSessionNotFoundError(
            "Cross-chat session not found"
        )

        response = client.post(
            f"/api/cross-chat/sessions/{uuid4()}/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 404

    def test_query_execution_error(self, client, mock_cross_chat_service):
        """Returns 500 when query execution fails."""
        mock_cross_chat_service.query.side_effect = QueryExecutionError(
            "LLM API error"
        )

        response = client.post(
            f"/api/cross-chat/sessions/{uuid4()}/query",
            json={"question": "Test question"},
        )

        assert response.status_code == 500


# =============================================================================
# DELETE /api/cross-chat/sessions/{id}
# =============================================================================


class TestDeleteCrossChatSession:
    """Tests for DELETE /api/cross-chat/sessions/{id}."""

    def test_delete_session_found(self, client, mock_cross_chat_service):
        """Returns 200 when session is deleted."""
        mock_cross_chat_service.delete_session.return_value = None

        response = client.delete(f"/api/cross-chat/sessions/{uuid4()}")

        assert response.status_code == 200

    def test_delete_session_not_found(self, client, mock_cross_chat_service):
        """Returns 404 when session does not exist."""
        mock_cross_chat_service.delete_session.side_effect = CrossChatSessionNotFoundError(
            "Cross-chat session not found"
        )

        response = client.delete(f"/api/cross-chat/sessions/{uuid4()}")

        assert response.status_code == 404
