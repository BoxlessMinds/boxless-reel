"""Tests for AgentService."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents import AgentConfig, AgentResponse, Citation
from src.agents.exceptions import QueryError
from src.agents.knowledge import IndexingError as KBIndexingError
from src.models.transcript import Transcript
from src.repositories import TranscriptRepository
from src.services import (
    AgentNotAvailableError,
    AgentService,
    IndexingError,
    QueryExecutionError,
    QueryResponse,
    SessionInfo,
    SessionNotFoundError,
    TranscriptNotFoundError,
)


# --- Fixtures ---


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock TranscriptRepository."""
    return MagicMock(spec=TranscriptRepository)


@pytest.fixture
def mock_transcript() -> MagicMock:
    """Create a mock Transcript object."""
    transcript = MagicMock(spec=Transcript)
    transcript.id = "test-transcript-id"
    transcript.video_id = "dQw4w9WgXcQ"
    transcript.title = "Test Video Title"
    transcript.channel_name = "Test Channel"
    transcript.duration_seconds = 212
    transcript.transcript_text = "This is a test transcript."
    transcript.transcript_segments = [
        {"text": "This is a test", "start": 0.0, "duration": 2.5},
        {"text": "transcript.", "start": 2.5, "duration": 2.0},
    ]
    return transcript


@pytest.fixture
def enabled_config() -> MagicMock:
    """Create a mock AgentConfig with API keys enabled."""
    config = MagicMock(spec=AgentConfig)
    config.is_enabled = True
    config.validate_provider.return_value = "anthropic"
    config.get_model_id.return_value = "claude-sonnet-4-5"
    return config


@pytest.fixture
def disabled_config() -> MagicMock:
    """Create a mock AgentConfig with no API keys."""
    config = MagicMock(spec=AgentConfig)
    config.is_enabled = False
    return config


@pytest.fixture
def mock_knowledge_base() -> MagicMock:
    """Create a mock TranscriptKnowledgeBase."""
    kb = MagicMock()
    kb.is_indexed.return_value = True
    kb.load_transcript.return_value = 10
    return kb


@pytest.fixture
def mock_agent_response() -> AgentResponse:
    """Create a sample AgentResponse."""
    return AgentResponse(
        content="This is the answer based on the transcript.",
        citations=[
            Citation(
                text="This is a test",
                start_time=0.0,
                end_time=2.5,
            )
        ],
        session_id="test-session-id",
        model_used="claude-sonnet-4-5",
        search_results_used=1,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def service_with_mocks(
    mock_repository: MagicMock,
    mock_transcript: MagicMock,
    enabled_config: MagicMock,
    mock_knowledge_base: MagicMock,
) -> AgentService:
    """Create an AgentService with mocked dependencies."""
    mock_repository.get_by_id.return_value = mock_transcript
    service = AgentService(mock_repository, config=enabled_config)
    service._knowledge_base = mock_knowledge_base
    return service


# --- SessionInfo Tests ---


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_session_info_creation(self):
        """SessionInfo creates with all fields."""
        session = SessionInfo(
            session_id="session-123",
            transcript_id="transcript-456",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )

        assert session.session_id == "session-123"
        assert session.transcript_id == "transcript-456"
        assert session.video_id == "dQw4w9WgXcQ"
        assert session.video_title == "Test Video"
        assert session.model_provider == "anthropic"
        assert session.model_id == "claude-sonnet-4-5"
        assert session.query_count == 0
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_activity, datetime)

    def test_session_info_to_dict(self):
        """SessionInfo.to_dict returns correct dictionary."""
        session = SessionInfo(
            session_id="session-123",
            transcript_id="transcript-456",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
            query_count=5,
        )

        result = session.to_dict()

        assert result["session_id"] == "session-123"
        assert result["transcript_id"] == "transcript-456"
        assert result["video_id"] == "dQw4w9WgXcQ"
        assert result["video_title"] == "Test Video"
        assert result["model_provider"] == "anthropic"
        assert result["model_id"] == "claude-sonnet-4-5"
        assert result["query_count"] == 5
        assert "created_at" in result
        assert "last_activity" in result


# --- QueryResponse Tests ---


class TestQueryResponse:
    """Tests for QueryResponse dataclass."""

    def test_query_response_creation(self):
        """QueryResponse creates with all fields."""
        now = datetime.now(timezone.utc)
        response = QueryResponse(
            content="Test answer",
            citations=[{"text": "quote", "start_time": 0.0}],
            session_id="session-123",
            model_used="claude-sonnet-4-5",
            search_results_used=3,
            created_at=now,
        )

        assert response.content == "Test answer"
        assert len(response.citations) == 1
        assert response.session_id == "session-123"
        assert response.model_used == "claude-sonnet-4-5"
        assert response.search_results_used == 3
        assert response.created_at == now

    def test_query_response_to_dict(self):
        """QueryResponse.to_dict returns correct dictionary."""
        now = datetime.now(timezone.utc)
        response = QueryResponse(
            content="Test answer",
            citations=[{"text": "quote", "start_time": 0.0}],
            session_id="session-123",
            model_used="claude-sonnet-4-5",
            search_results_used=3,
            created_at=now,
        )

        result = response.to_dict()

        assert result["content"] == "Test answer"
        assert result["citations"] == [{"text": "quote", "start_time": 0.0}]
        assert result["session_id"] == "session-123"
        assert result["model_used"] == "claude-sonnet-4-5"
        assert result["search_results_used"] == 3
        assert result["created_at"] == now.isoformat()


# --- AgentService Initialization Tests ---


class TestAgentServiceInitialization:
    """Tests for AgentService initialization."""

    def test_init_with_repository(self, mock_repository: MagicMock):
        """AgentService initializes with repository."""
        with patch("src.services.agent_service.get_agent_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.is_enabled = True
            mock_get_config.return_value = mock_config

            service = AgentService(mock_repository)

            assert service.repository == mock_repository
            assert service.config == mock_config
            assert service._sessions == {}
            assert service._agents == {}
            assert service._knowledge_base is None

    def test_init_with_custom_config(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """AgentService uses provided config instead of default."""
        service = AgentService(mock_repository, config=enabled_config)

        assert service.config == enabled_config

    def test_knowledge_base_lazy_loading(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """Knowledge base is lazily created on first access."""
        service = AgentService(mock_repository, config=enabled_config)

        assert service._knowledge_base is None

        with patch(
            "src.services.agent_service.TranscriptKnowledgeBase"
        ) as mock_kb_class:
            mock_kb = MagicMock()
            mock_kb_class.return_value = mock_kb

            result = service.knowledge_base

            mock_kb_class.assert_called_once_with(config=enabled_config)
            assert result == mock_kb

    def test_is_available_when_enabled(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """is_available returns True when config.is_enabled is True."""
        service = AgentService(mock_repository, config=enabled_config)

        assert service.is_available is True

    def test_is_available_when_disabled(
        self, mock_repository: MagicMock, disabled_config: MagicMock
    ):
        """is_available returns False when config.is_enabled is False."""
        service = AgentService(mock_repository, config=disabled_config)

        assert service.is_available is False


# --- AgentService Availability Tests ---


class TestAgentServiceAvailability:
    """Tests for agent availability checks."""

    def test_ensure_available_raises_when_disabled(
        self, mock_repository: MagicMock, disabled_config: MagicMock
    ):
        """_ensure_available raises AgentNotAvailableError when disabled."""
        service = AgentService(mock_repository, config=disabled_config)

        with pytest.raises(AgentNotAvailableError) as exc_info:
            service._ensure_available()

        assert "LLM API key" in str(exc_info.value)

    def test_ensure_available_succeeds_when_enabled(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """_ensure_available does not raise when enabled."""
        service = AgentService(mock_repository, config=enabled_config)

        # Should not raise
        service._ensure_available()


# --- Transcript Lookup Tests ---


class TestTranscriptLookup:
    """Tests for transcript lookup."""

    def test_get_transcript_or_raise_success(
        self, service_with_mocks: AgentService, mock_transcript: MagicMock
    ):
        """_get_transcript_or_raise returns transcript when found."""
        result = service_with_mocks._get_transcript_or_raise("test-transcript-id")

        assert result == mock_transcript

    def test_get_transcript_or_raise_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """_get_transcript_or_raise raises TranscriptNotFoundError when not found."""
        mock_repository.get_by_id.return_value = None
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(TranscriptNotFoundError) as exc_info:
            service._get_transcript_or_raise("nonexistent-id")

        assert "nonexistent-id" in str(exc_info.value)


# --- Indexing Tests ---


class TestAgentServiceIndexing:
    """Tests for transcript indexing."""

    def test_index_transcript_success(
        self, service_with_mocks: AgentService, mock_knowledge_base: MagicMock
    ):
        """index_transcript successfully indexes a transcript."""
        mock_knowledge_base.load_transcript.return_value = 15

        result = service_with_mocks.index_transcript("test-transcript-id")

        assert result == 15
        mock_knowledge_base.load_transcript.assert_called_once()

    def test_index_transcript_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """index_transcript raises TranscriptNotFoundError for missing transcript."""
        mock_repository.get_by_id.return_value = None
        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = MagicMock()

        with pytest.raises(TranscriptNotFoundError):
            service.index_transcript("nonexistent-id")

    def test_index_transcript_not_available(
        self, mock_repository: MagicMock, disabled_config: MagicMock
    ):
        """index_transcript raises AgentNotAvailableError when disabled."""
        service = AgentService(mock_repository, config=disabled_config)

        with pytest.raises(AgentNotAvailableError):
            service.index_transcript("test-transcript-id")

    def test_index_transcript_indexing_error(
        self,
        service_with_mocks: AgentService,
        mock_knowledge_base: MagicMock,
    ):
        """index_transcript raises IndexingError when knowledge base fails."""
        mock_knowledge_base.load_transcript.side_effect = KBIndexingError("KB error")

        with pytest.raises(IndexingError) as exc_info:
            service_with_mocks.index_transcript("test-transcript-id")

        assert "KB error" in str(exc_info.value)

    def test_is_indexed_true(
        self, service_with_mocks: AgentService, mock_knowledge_base: MagicMock
    ):
        """is_indexed returns True when transcript is indexed."""
        mock_knowledge_base.is_indexed.return_value = True

        result = service_with_mocks.is_indexed("test-transcript-id")

        assert result is True
        mock_knowledge_base.is_indexed.assert_called_with("test-transcript-id")

    def test_is_indexed_false(
        self, service_with_mocks: AgentService, mock_knowledge_base: MagicMock
    ):
        """is_indexed returns False when transcript is not indexed."""
        mock_knowledge_base.is_indexed.return_value = False

        result = service_with_mocks.is_indexed("test-transcript-id")

        assert result is False


# --- Session Management Tests ---


class TestAgentServiceSessionManagement:
    """Tests for session management."""

    def test_create_session_success(
        self,
        mock_repository: MagicMock,
        mock_transcript: MagicMock,
        enabled_config: MagicMock,
        mock_knowledge_base: MagicMock,
    ):
        """create_session creates a new session successfully."""
        mock_repository.get_by_id.return_value = mock_transcript
        mock_knowledge_base.is_indexed.return_value = True

        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = mock_knowledge_base

        with patch(
            "src.services.agent_service.TranscriptQueryAgent"
        ) as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            result = service.create_session("test-transcript-id", "anthropic")

            assert isinstance(result, SessionInfo)
            assert result.transcript_id == "test-transcript-id"
            assert result.video_id == "dQw4w9WgXcQ"
            assert result.video_title == "Test Video Title"
            assert result.model_provider == "anthropic"
            assert result.session_id in service._sessions
            assert result.session_id in service._agents

    def test_create_session_auto_indexes(
        self,
        mock_repository: MagicMock,
        mock_transcript: MagicMock,
        enabled_config: MagicMock,
        mock_knowledge_base: MagicMock,
    ):
        """create_session auto-indexes transcript if not already indexed."""
        mock_repository.get_by_id.return_value = mock_transcript
        mock_knowledge_base.is_indexed.return_value = False
        mock_knowledge_base.load_transcript.return_value = 10

        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = mock_knowledge_base

        with patch(
            "src.services.agent_service.TranscriptQueryAgent"
        ) as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            service.create_session("test-transcript-id")

            mock_knowledge_base.load_transcript.assert_called_once()

    def test_create_session_not_available(
        self, mock_repository: MagicMock, disabled_config: MagicMock
    ):
        """create_session raises AgentNotAvailableError when disabled."""
        service = AgentService(mock_repository, config=disabled_config)

        with pytest.raises(AgentNotAvailableError):
            service.create_session("test-transcript-id")

    def test_create_session_transcript_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """create_session raises TranscriptNotFoundError for missing transcript."""
        mock_repository.get_by_id.return_value = None
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(TranscriptNotFoundError):
            service.create_session("nonexistent-id")

    def test_get_session_success(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """get_session returns session info for existing session."""
        service = AgentService(mock_repository, config=enabled_config)
        session_info = SessionInfo(
            session_id="test-session-id",
            transcript_id="test-transcript-id",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        service._sessions["test-session-id"] = session_info

        result = service.get_session("test-session-id")

        assert result == session_info

    def test_get_session_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """get_session raises SessionNotFoundError for missing session."""
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(SessionNotFoundError) as exc_info:
            service.get_session("nonexistent-session")

        assert "nonexistent-session" in str(exc_info.value)

    def test_delete_session_success(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """delete_session removes session from registry."""
        service = AgentService(mock_repository, config=enabled_config)
        session_info = SessionInfo(
            session_id="test-session-id",
            transcript_id="test-transcript-id",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        service._sessions["test-session-id"] = session_info
        service._agents["test-session-id"] = MagicMock()

        service.delete_session("test-session-id")

        assert "test-session-id" not in service._sessions
        assert "test-session-id" not in service._agents

    def test_delete_session_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """delete_session raises SessionNotFoundError for missing session."""
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(SessionNotFoundError):
            service.delete_session("nonexistent-session")

    def test_list_sessions_all(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """list_sessions returns all sessions."""
        service = AgentService(mock_repository, config=enabled_config)
        session1 = SessionInfo(
            session_id="session-1",
            transcript_id="transcript-1",
            video_id="vid1",
            video_title="Video 1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        session2 = SessionInfo(
            session_id="session-2",
            transcript_id="transcript-2",
            video_id="vid2",
            video_title="Video 2",
            model_provider="openai",
            model_id="gpt-4o",
        )
        service._sessions["session-1"] = session1
        service._sessions["session-2"] = session2

        result = service.list_sessions()

        assert len(result) == 2
        assert session1 in result
        assert session2 in result

    def test_list_sessions_filtered(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """list_sessions filters by transcript_id."""
        service = AgentService(mock_repository, config=enabled_config)
        session1 = SessionInfo(
            session_id="session-1",
            transcript_id="transcript-1",
            video_id="vid1",
            video_title="Video 1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        session2 = SessionInfo(
            session_id="session-2",
            transcript_id="transcript-2",
            video_id="vid2",
            video_title="Video 2",
            model_provider="openai",
            model_id="gpt-4o",
        )
        service._sessions["session-1"] = session1
        service._sessions["session-2"] = session2

        result = service.list_sessions(transcript_id="transcript-1")

        assert len(result) == 1
        assert session1 in result

    def test_get_session_history_success(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """get_session_history returns conversation history."""
        service = AgentService(mock_repository, config=enabled_config)
        mock_agent = MagicMock()
        mock_agent.get_session_history.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        service._agents["test-session-id"] = mock_agent

        result = service.get_session_history("test-session-id")

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_get_session_history_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """get_session_history raises SessionNotFoundError for missing session."""
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(SessionNotFoundError):
            service.get_session_history("nonexistent-session")


# --- Query Tests ---


class TestAgentServiceQuery:
    """Tests for query execution."""

    def test_query_success(
        self,
        mock_repository: MagicMock,
        enabled_config: MagicMock,
        mock_agent_response: AgentResponse,
    ):
        """query executes successfully and returns QueryResponse."""
        service = AgentService(mock_repository, config=enabled_config)
        session_info = SessionInfo(
            session_id="test-session-id",
            transcript_id="test-transcript-id",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        mock_agent = MagicMock()
        mock_agent.query.return_value = mock_agent_response

        service._sessions["test-session-id"] = session_info
        service._agents["test-session-id"] = mock_agent

        result = service.query("test-session-id", "What is discussed?")

        assert isinstance(result, QueryResponse)
        assert result.content == mock_agent_response.content
        assert result.session_id == "test-session-id"
        assert result.model_used == "claude-sonnet-4-5"
        assert session_info.query_count == 1

    def test_query_session_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """query raises SessionNotFoundError for missing session."""
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(SessionNotFoundError):
            service.query("nonexistent-session", "What is this about?")

    def test_query_execution_error(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """query raises QueryExecutionError when agent.query fails."""
        service = AgentService(mock_repository, config=enabled_config)
        session_info = SessionInfo(
            session_id="test-session-id",
            transcript_id="test-transcript-id",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
        )
        mock_agent = MagicMock()
        mock_agent.query.side_effect = QueryError("LLM timeout")

        service._sessions["test-session-id"] = session_info
        service._agents["test-session-id"] = mock_agent

        with pytest.raises(QueryExecutionError) as exc_info:
            service.query("test-session-id", "What is this about?")

        assert "LLM timeout" in str(exc_info.value)

    def test_query_updates_session_metadata(
        self,
        mock_repository: MagicMock,
        enabled_config: MagicMock,
        mock_agent_response: AgentResponse,
    ):
        """query updates session last_activity and query_count."""
        from datetime import timedelta

        service = AgentService(mock_repository, config=enabled_config)
        # Set initial time to the past to ensure last_activity is updated
        initial_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        session_info = SessionInfo(
            session_id="test-session-id",
            transcript_id="test-transcript-id",
            video_id="dQw4w9WgXcQ",
            video_title="Test Video",
            model_provider="anthropic",
            model_id="claude-sonnet-4-5",
            last_activity=initial_time,
            query_count=0,
        )
        mock_agent = MagicMock()
        mock_agent.query.return_value = mock_agent_response

        service._sessions["test-session-id"] = session_info
        service._agents["test-session-id"] = mock_agent

        service.query("test-session-id", "First question")
        service.query("test-session-id", "Second question")

        assert session_info.query_count == 2
        assert session_info.last_activity > initial_time


# --- One-Shot Query Tests ---


class TestAgentServiceQueryOneshot:
    """Tests for one-shot query execution."""

    def test_query_oneshot_success(
        self,
        mock_repository: MagicMock,
        mock_transcript: MagicMock,
        enabled_config: MagicMock,
        mock_knowledge_base: MagicMock,
        mock_agent_response: AgentResponse,
    ):
        """query_oneshot executes successfully."""
        mock_repository.get_by_id.return_value = mock_transcript
        mock_knowledge_base.is_indexed.return_value = True

        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = mock_knowledge_base

        with patch(
            "src.services.agent_service.TranscriptQueryAgent"
        ) as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent.query.return_value = mock_agent_response
            mock_agent_class.return_value = mock_agent

            result = service.query_oneshot(
                "test-transcript-id", "What is this about?"
            )

            assert isinstance(result, QueryResponse)
            assert result.content == mock_agent_response.content
            assert result.session_id == ""  # No session for one-shot

    def test_query_oneshot_auto_indexes(
        self,
        mock_repository: MagicMock,
        mock_transcript: MagicMock,
        enabled_config: MagicMock,
        mock_knowledge_base: MagicMock,
        mock_agent_response: AgentResponse,
    ):
        """query_oneshot auto-indexes transcript if not already indexed."""
        mock_repository.get_by_id.return_value = mock_transcript
        mock_knowledge_base.is_indexed.return_value = False
        mock_knowledge_base.load_transcript.return_value = 10

        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = mock_knowledge_base

        with patch(
            "src.services.agent_service.TranscriptQueryAgent"
        ) as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent.query.return_value = mock_agent_response
            mock_agent_class.return_value = mock_agent

            service.query_oneshot("test-transcript-id", "What is this about?")

            mock_knowledge_base.load_transcript.assert_called_once()

    def test_query_oneshot_not_available(
        self, mock_repository: MagicMock, disabled_config: MagicMock
    ):
        """query_oneshot raises AgentNotAvailableError when disabled."""
        service = AgentService(mock_repository, config=disabled_config)

        with pytest.raises(AgentNotAvailableError):
            service.query_oneshot("test-transcript-id", "What is this about?")

    def test_query_oneshot_transcript_not_found(
        self, mock_repository: MagicMock, enabled_config: MagicMock
    ):
        """query_oneshot raises TranscriptNotFoundError for missing transcript."""
        mock_repository.get_by_id.return_value = None
        service = AgentService(mock_repository, config=enabled_config)

        with pytest.raises(TranscriptNotFoundError):
            service.query_oneshot("nonexistent-id", "What is this about?")

    def test_query_oneshot_execution_error(
        self,
        mock_repository: MagicMock,
        mock_transcript: MagicMock,
        enabled_config: MagicMock,
        mock_knowledge_base: MagicMock,
    ):
        """query_oneshot raises QueryExecutionError when agent.query fails."""
        mock_repository.get_by_id.return_value = mock_transcript
        mock_knowledge_base.is_indexed.return_value = True

        service = AgentService(mock_repository, config=enabled_config)
        service._knowledge_base = mock_knowledge_base

        with patch(
            "src.services.agent_service.TranscriptQueryAgent"
        ) as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent.query.side_effect = QueryError("LLM error")
            mock_agent_class.return_value = mock_agent

            with pytest.raises(QueryExecutionError) as exc_info:
                service.query_oneshot("test-transcript-id", "What is this about?")

            assert "LLM error" in str(exc_info.value)


# --- Exception Tests ---


class TestAgentServiceExceptions:
    """Tests for exception types."""

    def test_agent_not_available_error_inheritance(self):
        """AgentNotAvailableError inherits from AgentServiceError."""
        from src.services.exceptions import AgentServiceError

        error = AgentNotAvailableError("No API keys")
        assert isinstance(error, AgentServiceError)
        assert isinstance(error, Exception)

    def test_session_not_found_error_inheritance(self):
        """SessionNotFoundError inherits from AgentServiceError."""
        from src.services.exceptions import AgentServiceError

        error = SessionNotFoundError("Session not found")
        assert isinstance(error, AgentServiceError)

    def test_transcript_not_found_error_inheritance(self):
        """TranscriptNotFoundError inherits from AgentServiceError."""
        from src.services.exceptions import AgentServiceError

        error = TranscriptNotFoundError("Transcript not found")
        assert isinstance(error, AgentServiceError)

    def test_indexing_error_inheritance(self):
        """IndexingError inherits from AgentServiceError."""
        from src.services.exceptions import AgentServiceError

        error = IndexingError("Indexing failed")
        assert isinstance(error, AgentServiceError)

    def test_query_execution_error_inheritance(self):
        """QueryExecutionError inherits from AgentServiceError."""
        from src.services.exceptions import AgentServiceError

        error = QueryExecutionError("Query failed")
        assert isinstance(error, AgentServiceError)
