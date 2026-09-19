"""Tests for CrossChatService business logic."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.services.cross_chat_service import CrossChatService
from src.services.exceptions import (
    CrossChatSessionNotFoundError,
    CrossChatValidationError,
)


# --- Fixtures ---


@pytest.fixture
def mock_cross_chat_repo():
    """Create a mock CrossChatRepository."""
    return MagicMock()


@pytest.fixture
def mock_session_repo():
    """Create a mock SessionRepository."""
    return MagicMock()


@pytest.fixture
def mock_transcript_repo():
    """Create a mock TranscriptRepository."""
    return MagicMock()


@pytest.fixture
def mock_config():
    """Create a mock AgentConfig with agent features enabled."""
    config = MagicMock()
    config.is_enabled = True
    config.validate_provider.return_value = "anthropic"
    config.get_model_id.return_value = "claude-sonnet-4-5-20250929"
    config.max_context_chunks = 10
    return config


@pytest.fixture
def cross_chat_service(mock_cross_chat_repo, mock_session_repo, mock_transcript_repo, mock_config):
    """Create a CrossChatService with mocked dependencies."""
    return CrossChatService(
        cross_chat_repository=mock_cross_chat_repo,
        session_repository=mock_session_repo,
        transcript_repository=mock_transcript_repo,
        config=mock_config,
    )


def _mock_cross_chat_session(session_id=None, user_id="user-1"):
    """Build a mock CrossChatSession object."""
    mock = MagicMock()
    mock.id = session_id or str(uuid4())
    mock.user_id = user_id
    mock.model_provider = "anthropic"
    mock.model_name = "claude-sonnet-4-5-20250929"
    mock.created_at = datetime.now(timezone.utc)
    mock.updated_at = datetime.now(timezone.utc)
    mock.referenced_sessions = []
    mock.messages = []
    return mock


# --- Create session tests ---


class TestCrossChatServiceCreateSession:
    """Tests for CrossChatService.create_session()."""

    @patch.object(CrossChatService, "_create_cross_chat_agent")
    def test_create_session_with_valid_session_ids(
        self, mock_create_agent, cross_chat_service, mock_session_repo, mock_cross_chat_repo
    ):
        """create_session succeeds when all session IDs are valid."""
        s1_id = str(uuid4())
        s2_id = str(uuid4())
        user_id = "user-1"

        # Build mock sessions with proper transcript attributes
        def _make_agent_session(sid, tid, title, video_id):
            s = MagicMock()
            s.id = sid
            s.user_id = user_id
            s.transcript = MagicMock()
            s.transcript.id = tid
            s.transcript.title = title
            s.transcript.video_id = video_id
            s.transcript.transcript_text = f"Transcript for {video_id}"
            s.transcript.transcript_segments = [{"text": "hi", "start": 0.0, "duration": 1.0}]
            return s

        mock_s1 = _make_agent_session(s1_id, "tid-1", "Video One", "vid1")
        mock_s2 = _make_agent_session(s2_id, "tid-2", "Video Two", "vid2")

        mock_session_repo.get_with_transcript.side_effect = lambda sid, user_id=None: (
            mock_s1 if sid == s1_id else mock_s2 if sid == s2_id else None
        )

        # Mock knowledge base indexing
        cross_chat_service._knowledge_base = MagicMock()
        cross_chat_service._knowledge_base.is_indexed.return_value = True

        expected = _mock_cross_chat_session(user_id=user_id)
        mock_cross_chat_repo.create.return_value = expected

        result = cross_chat_service.create_session(
            session_ids=[s1_id, s2_id],
            user_id=user_id,
            model_provider="anthropic",
        )

        assert result is not None
        mock_cross_chat_repo.create.assert_called_once()
        mock_create_agent.assert_called_once()

    def test_create_session_invalid_session_id_raises(
        self, cross_chat_service, mock_session_repo
    ):
        """create_session raises CrossChatValidationError for invalid session IDs."""
        mock_session_repo.get_with_transcript.return_value = None

        with pytest.raises(CrossChatValidationError):
            cross_chat_service.create_session(
                session_ids=[str(uuid4()), str(uuid4())],
                user_id="user-1",
                model_provider="anthropic",
            )

    def test_create_session_fewer_than_2_raises(self, cross_chat_service):
        """create_session raises CrossChatValidationError when fewer than 2 session IDs provided."""
        with pytest.raises(CrossChatValidationError):
            cross_chat_service.create_session(
                session_ids=[str(uuid4())],
                user_id="user-1",
                model_provider="anthropic",
            )


# --- Query tests ---


class TestCrossChatServiceQuery:
    """Tests for CrossChatService.query()."""

    def test_query_execution_flow(
        self,
        cross_chat_service,
        mock_cross_chat_repo,
    ):
        """query() retrieves session, runs agent query, and saves messages."""
        session_id = str(uuid4())
        user_id = "user-1"

        mock_session = _mock_cross_chat_session(session_id=session_id, user_id=user_id)
        mock_cross_chat_repo.get_with_details.return_value = mock_session

        mock_response = MagicMock()
        mock_response.content = "Here is the answer."
        mock_response.citations = []
        mock_response.model_used = "claude-sonnet-4-5-20250929"
        mock_response.transcript_results_used = 3
        mock_response.web_results_used = 0
        mock_response.created_at = datetime.now(timezone.utc)

        # Pre-populate agent registry so query() doesn't try to restore
        mock_agent = MagicMock()
        mock_agent.query.return_value = mock_response
        mock_agent._last_search_results = []
        cross_chat_service._agents[session_id] = mock_agent

        result = cross_chat_service.query(
            cross_chat_id=session_id,
            user_id=user_id,
            question="What do these videos have in common?",
        )

        assert result is not None
        assert result["content"] == "Here is the answer."
        mock_agent.query.assert_called_once_with("What do these videos have in common?")
        # Verify both user and assistant messages were saved
        assert mock_cross_chat_repo.add_message.call_count == 2


# --- Get session tests ---


class TestCrossChatServiceGetSession:
    """Tests for CrossChatService.get_session()."""

    def test_get_session_found(self, cross_chat_service, mock_cross_chat_repo):
        """get_session returns session when found."""
        session_id = str(uuid4())
        expected = _mock_cross_chat_session(session_id=session_id)
        mock_cross_chat_repo.get_with_details.return_value = expected

        result = cross_chat_service.get_session(session_id, user_id="user-1")

        assert result is not None

    def test_get_session_not_found(self, cross_chat_service, mock_cross_chat_repo):
        """get_session raises CrossChatSessionNotFoundError when not found."""
        mock_cross_chat_repo.get_with_details.return_value = None
        mock_cross_chat_repo.get_by_id.return_value = None

        with pytest.raises(CrossChatSessionNotFoundError):
            cross_chat_service.get_session(str(uuid4()), user_id="user-1")


# --- List sessions tests ---


class TestCrossChatServiceListSessions:
    """Tests for CrossChatService.list_sessions()."""

    def test_list_sessions_returns_all(self, cross_chat_service, mock_cross_chat_repo):
        """list_sessions returns all sessions for the user."""
        mock_cross_chat_repo.list_all.return_value = [
            _mock_cross_chat_session(),
            _mock_cross_chat_session(),
        ]

        result = cross_chat_service.list_sessions(user_id="user-1")

        assert len(result) == 2
        mock_cross_chat_repo.list_all.assert_called_once_with("user-1")


# --- Delete session tests ---


class TestCrossChatServiceDeleteSession:
    """Tests for CrossChatService.delete_session()."""

    def test_delete_session_found(self, cross_chat_service, mock_cross_chat_repo):
        """delete_session succeeds when session exists."""
        mock_cross_chat_repo.get_by_id.return_value = _mock_cross_chat_session()
        mock_cross_chat_repo.delete.return_value = True

        cross_chat_service.delete_session(str(uuid4()), user_id="user-1")

        mock_cross_chat_repo.delete.assert_called_once()

    def test_delete_session_not_found(self, cross_chat_service, mock_cross_chat_repo):
        """delete_session raises CrossChatSessionNotFoundError when not found."""
        mock_cross_chat_repo.get_by_id.return_value = None
        mock_cross_chat_repo.delete.return_value = False

        with pytest.raises(CrossChatSessionNotFoundError):
            cross_chat_service.delete_session(str(uuid4()), user_id="user-1")
