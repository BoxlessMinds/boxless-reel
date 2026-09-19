"""Tests for TranscriptQueryAgent and related components."""

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents import (
    AgentNotConfiguredError,
    AgentResponse,
    Citation,
    TranscriptNotIndexedError,
    TranscriptQueryAgent,
)
from src.agents.config import AgentConfig
from src.agents.knowledge import ChunkResult
from src.agents.prompts import (
    AGENT_INSTRUCTIONS,
    TRANSCRIPT_AGENT_SYSTEM_PROMPT,
    format_search_results,
    format_system_prompt,
)


class TestCitation:
    """Tests for Citation dataclass."""

    def test_citation_creation(self) -> None:
        """Test basic citation creation."""
        citation = Citation(
            text="Sample quote from video",
            start_time=125.5,
            end_time=130.0,
        )

        assert citation.text == "Sample quote from video"
        assert citation.start_time == 125.5
        assert citation.end_time == 130.0
        assert citation.timestamp_formatted == "02:05"

    def test_citation_auto_formats_timestamp(self) -> None:
        """Test timestamp is auto-formatted on creation."""
        citation = Citation(text="Test", start_time=65.0)

        assert citation.timestamp_formatted == "01:05"

    def test_citation_respects_provided_timestamp(self) -> None:
        """Test provided timestamp is not overwritten."""
        citation = Citation(
            text="Test",
            start_time=65.0,
            timestamp_formatted="custom",
        )

        assert citation.timestamp_formatted == "custom"

    def test_citation_to_dict(self) -> None:
        """Test dictionary conversion."""
        citation = Citation(
            text="Quote",
            start_time=90.0,
            end_time=95.0,
        )

        result = citation.to_dict()

        assert result["text"] == "Quote"
        assert result["start_time"] == 90.0
        assert result["end_time"] == 95.0
        assert result["timestamp_formatted"] == "01:30"


class TestAgentResponse:
    """Tests for AgentResponse dataclass."""

    def test_response_creation(self) -> None:
        """Test basic response creation."""
        response = AgentResponse(
            content="This is the response",
            model_used="claude-sonnet-4-5",
            search_results_used=3,
        )

        assert response.content == "This is the response"
        assert response.citations == []
        assert response.session_id is None
        assert response.model_used == "claude-sonnet-4-5"
        assert response.search_results_used == 3
        assert isinstance(response.created_at, datetime)

    def test_response_with_citations(self) -> None:
        """Test response with citations."""
        citations = [
            Citation(text="Quote 1", start_time=10.0),
            Citation(text="Quote 2", start_time=20.0),
        ]
        response = AgentResponse(
            content="Response with citations",
            citations=citations,
        )

        assert len(response.citations) == 2
        assert response.citations[0].text == "Quote 1"

    def test_response_to_dict(self) -> None:
        """Test dictionary conversion."""
        response = AgentResponse(
            content="Test response",
            citations=[Citation(text="Quote", start_time=5.0)],
            session_id="session-123",
            model_used="gpt-4o",
            search_results_used=1,
        )

        result = response.to_dict()

        assert result["content"] == "Test response"
        assert len(result["citations"]) == 1
        assert result["session_id"] == "session-123"
        assert result["model_used"] == "gpt-4o"
        assert result["search_results_used"] == 1
        assert "created_at" in result


class TestPrompts:
    """Tests for prompts module."""

    def test_system_prompt_template_exists(self) -> None:
        """Verify system prompt template is defined."""
        assert TRANSCRIPT_AGENT_SYSTEM_PROMPT is not None
        assert len(TRANSCRIPT_AGENT_SYSTEM_PROMPT) > 100

    def test_agent_instructions_exist(self) -> None:
        """Verify agent instructions are defined."""
        assert len(AGENT_INSTRUCTIONS) >= 3
        assert all(isinstance(i, str) for i in AGENT_INSTRUCTIONS)

    def test_format_system_prompt_with_all_fields(self) -> None:
        """Test formatting with all metadata."""
        result = format_system_prompt(
            title="Python Tutorial",
            channel="CodeChannel",
            duration_seconds=3661,  # 61:01
        )

        assert "Python Tutorial" in result
        assert "CodeChannel" in result
        assert "61:01" in result

    def test_format_system_prompt_with_missing_fields(self) -> None:
        """Test formatting with missing optional fields."""
        result = format_system_prompt(
            title="Video Title",
            channel=None,
            duration_seconds=None,
        )

        assert "Video Title" in result
        assert "Unknown" in result  # For channel and duration

    def test_format_search_results_empty(self) -> None:
        """Test formatting empty results."""
        result = format_search_results([])

        assert "No relevant content found" in result

    def test_format_search_results_with_chunks(self) -> None:
        """Test formatting search results."""
        results = [
            ChunkResult(
                text="First chunk",
                start_time=0.0,
                end_time=5.0,
                transcript_id="t1",
                video_id="v1",
                score=0.9,
            ),
            ChunkResult(
                text="Second chunk",
                start_time=10.0,
                end_time=15.0,
                transcript_id="t1",
                video_id="v1",
                score=0.8,
            ),
        ]

        result = format_search_results(results)

        assert "[00:00]" in result
        assert "First chunk" in result
        assert "[00:10]" in result
        assert "Second chunk" in result
        assert "---" in result  # Separator


class TestTranscriptQueryAgent:
    """Tests for TranscriptQueryAgent class."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> AgentConfig:
        """Mock agent config for testing."""
        return AgentConfig(
            openai_api_key="test-openai-key",
            anthropic_api_key="test-anthropic-key",
            default_llm_provider="anthropic",
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=10,
            chunk_size=500,
            chunk_overlap=100,
        )

    @pytest.fixture
    def mock_config_no_keys(self, tmp_path: Path) -> AgentConfig:
        """Mock config with no API keys."""
        return AgentConfig(
            openai_api_key=None,
            anthropic_api_key=None,
            default_llm_provider="anthropic",
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=10,
            chunk_size=500,
            chunk_overlap=100,
        )

    @pytest.fixture
    def mock_knowledge_base(self) -> MagicMock:
        """Mock knowledge base that appears indexed."""
        kb = MagicMock()
        kb.is_indexed.return_value = True
        kb.search.return_value = [
            ChunkResult(
                text="Sample content from transcript",
                start_time=10.0,
                end_time=15.0,
                transcript_id="test-transcript",
                video_id="test-video",
                score=0.9,
            )
        ]
        return kb

    def test_init_requires_api_keys(self, mock_config_no_keys: AgentConfig) -> None:
        """Agent raises error if no API keys configured."""
        with pytest.raises(AgentNotConfiguredError, match="API key"):
            TranscriptQueryAgent(
                transcript_id="test-id",
                video_title="Test Video",
                video_id="abc123",
                config=mock_config_no_keys,
            )

    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    def test_init_requires_indexed_transcript(
        self, mock_kb_class: MagicMock, mock_config: AgentConfig
    ) -> None:
        """Agent raises error if transcript not indexed."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = False
        mock_kb_class.return_value = mock_kb

        with pytest.raises(TranscriptNotIndexedError, match="not been indexed"):
            TranscriptQueryAgent(
                transcript_id="test-id",
                video_title="Test Video",
                video_id="abc123",
                config=mock_config,
            )

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_init_success(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Agent initializes successfully with valid config."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test Video",
            video_id="abc123",
            channel_name="Test Channel",
            duration_seconds=300,
            config=mock_config,
        )

        assert agent.transcript_id == "test-id"
        assert agent.video_title == "Test Video"
        assert agent.video_id == "abc123"
        assert agent.channel_name == "Test Channel"
        assert agent.duration_seconds == 300
        assert agent.model_provider == "anthropic"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_init_with_session_id(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Agent accepts and stores session_id."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            session_id="existing-session",
            config=mock_config,
        )

        assert agent.session_id == "existing-session"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_query_returns_agent_response(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Query returns properly structured AgentResponse."""
        # Setup mocks
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb.search.return_value = []
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        mock_run_result = MagicMock()
        mock_run_result.content = "This is the answer to your question."
        mock_run_result.session_id = None
        mock_agent_class.return_value.run.return_value = mock_run_result

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=mock_config,
        )

        response = agent.query("What is this video about?")

        assert isinstance(response, AgentResponse)
        assert response.content == "This is the answer to your question."
        assert response.model_used == "claude-sonnet-4-5"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_query_extracts_citations(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Citations are extracted from search results."""
        # Setup mocks
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        mock_run_result = MagicMock()
        mock_run_result.content = "Answer based on transcript."
        mock_run_result.session_id = None
        mock_agent_class.return_value.run.return_value = mock_run_result

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=mock_config,
        )

        # Simulate search results being stored (this happens during agent.run via tool)
        # We set them directly and test _extract_citations
        agent._last_search_results = [
            ChunkResult(
                text="Relevant quote from video",
                start_time=60.0,
                end_time=65.0,
                transcript_id="test-id",
                video_id="v1",
                score=0.9,
            ),
            ChunkResult(
                text="Another relevant section",
                start_time=120.0,
                end_time=125.0,
                transcript_id="test-id",
                video_id="v1",
                score=0.8,
            ),
        ]

        # Test citation extraction directly
        citations = agent._extract_citations()

        assert len(citations) == 2
        assert citations[0].timestamp_formatted == "01:00"
        assert citations[1].timestamp_formatted == "02:00"
        assert citations[0].text == "Relevant quote from video"
        assert citations[1].text == "Another relevant section"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_citation_text_truncated(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Long citation text is truncated."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=mock_config,
        )

        # Create a search result with very long text
        long_text = "x" * 500
        agent._last_search_results = [
            ChunkResult(
                text=long_text,
                start_time=0.0,
                end_time=10.0,
                transcript_id="test-id",
                video_id="v1",
                score=0.9,
            )
        ]

        # Test citation extraction directly (truncation logic)
        citations = agent._extract_citations()

        assert len(citations) == 1
        assert len(citations[0].text) <= 203  # 200 + "..."
        assert citations[0].text.endswith("...")

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_model_properties(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Model properties return correct values."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=mock_config,
        )

        assert agent.model_provider == "anthropic"
        assert agent.model_id == "claude-sonnet-4-5"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_provider_fallback(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent falls back to available provider."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        # Config with only OpenAI key
        config = AgentConfig(
            openai_api_key="openai-key",
            anthropic_api_key=None,  # No Anthropic key
            default_llm_provider="anthropic",  # Default requests Anthropic
            default_model="claude-sonnet-4-5",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=10,
            chunk_size=500,
            chunk_overlap=100,
        )

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=config,
        )

        # Should fall back to OpenAI
        assert agent.model_provider == "openai"

    @patch("src.agents.transcript_agent.Agent")
    @patch("src.agents.transcript_agent.SqliteDb")
    @patch("src.agents.transcript_agent.TranscriptKnowledgeBase")
    @patch.object(AgentConfig, "create_model")
    def test_get_session_history_empty_without_session(
        self,
        mock_create_model: MagicMock,
        mock_kb_class: MagicMock,
        mock_db_class: MagicMock,
        mock_agent_class: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Session history is empty without session_id."""
        mock_kb = MagicMock()
        mock_kb.is_indexed.return_value = True
        mock_kb_class.return_value = mock_kb
        mock_create_model.return_value = MagicMock()

        agent = TranscriptQueryAgent(
            transcript_id="test-id",
            video_title="Test",
            video_id="v1",
            config=mock_config,
        )

        history = agent.get_session_history()

        assert history == []


class TestExceptions:
    """Tests for agent exceptions."""

    def test_agent_not_configured_error(self) -> None:
        """Test AgentNotConfiguredError can be raised."""
        from src.agents.exceptions import AgentNotConfiguredError

        with pytest.raises(AgentNotConfiguredError):
            raise AgentNotConfiguredError("No API keys")

    def test_transcript_not_indexed_error(self) -> None:
        """Test TranscriptNotIndexedError can be raised."""
        from src.agents.exceptions import TranscriptNotIndexedError

        with pytest.raises(TranscriptNotIndexedError):
            raise TranscriptNotIndexedError("Not indexed")

    def test_query_error(self) -> None:
        """Test QueryError can be raised."""
        from src.agents.exceptions import QueryError

        with pytest.raises(QueryError):
            raise QueryError("Query failed")

    def test_session_not_found_error(self) -> None:
        """Test SessionNotFoundError can be raised."""
        from src.agents.exceptions import SessionNotFoundError

        with pytest.raises(SessionNotFoundError):
            raise SessionNotFoundError("Session not found")


@pytest.mark.integration
class TestTranscriptQueryAgentIntegration:
    """
    Integration tests that require actual API calls.

    These tests are skipped by default. Run with:
        pytest -m integration
    """

    @pytest.fixture
    def real_config(self, tmp_path: Path) -> AgentConfig:
        """Create config with real API keys from environment."""
        import os

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        # Try loading from settings if not in environment
        if not anthropic_key and not openai_key:
            try:
                from src.config import settings

                anthropic_key = settings.anthropic_api_key
                openai_key = settings.openai_api_key
            except Exception:
                pass

        if not anthropic_key and not openai_key:
            pytest.skip("No API keys available")

        return AgentConfig(
            openai_api_key=openai_key,
            anthropic_api_key=anthropic_key,
            default_llm_provider="anthropic" if anthropic_key else "openai",
            default_model="claude-sonnet-4-5" if anthropic_key else "gpt-4o",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=5,
            chunk_size=500,
            chunk_overlap=100,
        )

    @pytest.fixture
    def indexed_knowledge_base(
        self, real_config: AgentConfig
    ) -> tuple[str, Any]:
        """Create a knowledge base with indexed transcript."""
        from src.agents.knowledge import TranscriptKnowledgeBase

        kb = TranscriptKnowledgeBase(config=real_config)

        transcript_id = "integration-test-123"
        segments = [
            {
                "text": "Welcome to our Python programming tutorial.",
                "start": 0.0,
                "duration": 3.0,
            },
            {
                "text": "Today we will learn about functions and classes.",
                "start": 3.0,
                "duration": 3.0,
            },
            {
                "text": "Functions are reusable blocks of code that perform specific tasks.",
                "start": 6.0,
                "duration": 4.0,
            },
            {
                "text": "Classes help organize code using object-oriented programming.",
                "start": 10.0,
                "duration": 4.0,
            },
        ]
        transcript_text = " ".join(s["text"] for s in segments)

        kb.load_transcript(
            transcript_id=transcript_id,
            transcript_text=transcript_text,
            transcript_segments=segments,
            video_id="test-video-id",
        )

        return transcript_id, kb

    def test_full_query_flow(
        self,
        real_config: AgentConfig,
        indexed_knowledge_base: tuple[str, Any],
    ) -> None:
        """Test complete query flow with real LLM."""
        transcript_id, _ = indexed_knowledge_base

        agent = TranscriptQueryAgent(
            transcript_id=transcript_id,
            video_title="Python Tutorial",
            video_id="test-video-id",
            channel_name="Test Channel",
            duration_seconds=60,
            config=real_config,
        )

        response = agent.query("What topics are covered in this tutorial?")

        assert response.content
        assert len(response.content) > 10
        assert response.model_used
