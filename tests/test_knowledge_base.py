"""Tests for transcript knowledge base components."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents.config import AgentConfig
from src.agents.knowledge import (
    ChunkResult,
    TranscriptChunk,
    TranscriptChunker,
    TranscriptKnowledgeBase,
)
from src.agents.knowledge.exceptions import IndexingError


class TestTranscriptChunk:
    """Tests for TranscriptChunk dataclass."""

    def test_chunk_creation(self) -> None:
        """Test basic chunk creation with all fields."""
        chunk = TranscriptChunk(
            text="Hello world",
            start_time=10.5,
            end_time=15.0,
            segment_indices=(0, 1, 2),
        )

        assert chunk.text == "Hello world"
        assert chunk.start_time == 10.5
        assert chunk.end_time == 15.0
        assert chunk.segment_indices == (0, 1, 2)

    def test_chunk_duration_property(self) -> None:
        """Test duration calculation."""
        chunk = TranscriptChunk(
            text="Test",
            start_time=10.0,
            end_time=15.0,
        )

        assert chunk.duration == 5.0

    def test_chunk_duration_none_when_no_end_time(self) -> None:
        """Test duration is None when end_time is not set."""
        chunk = TranscriptChunk(
            text="Test",
            start_time=10.0,
        )

        assert chunk.duration is None

    def test_chunk_to_dict(self) -> None:
        """Test dictionary conversion."""
        chunk = TranscriptChunk(
            text="Test content",
            start_time=5.0,
            end_time=10.0,
        )

        result = chunk.to_dict()

        assert result["text"] == "Test content"
        assert result["start_time"] == 5.0
        assert result["end_time"] == 10.0


class TestTranscriptChunker:
    """Tests for TranscriptChunker class."""

    @pytest.fixture
    def chunker(self) -> TranscriptChunker:
        """Default chunker with standard settings."""
        return TranscriptChunker(chunk_size=500, chunk_overlap=100)

    @pytest.fixture
    def sample_segments(self) -> list[dict[str, Any]]:
        """Sample YouTube transcript segments."""
        return [
            {"text": "Hello and welcome to this video.", "start": 0.0, "duration": 3.0},
            {
                "text": "Today we'll learn about Python programming.",
                "start": 3.0,
                "duration": 2.5,
            },
            {
                "text": "Python is a great programming language.",
                "start": 5.5,
                "duration": 3.0,
            },
            {
                "text": "It's used for web development and data science.",
                "start": 8.5,
                "duration": 3.5,
            },
            {
                "text": "Let's start with the basics.",
                "start": 12.0,
                "duration": 2.0,
            },
        ]

    @pytest.fixture
    def long_segments(self) -> list[dict[str, Any]]:
        """Segments that will require multiple chunks."""
        # Create segments with enough text to exceed chunk_size
        segments = []
        for i in range(20):
            segments.append(
                {
                    "text": f"This is segment number {i}. "
                    "It contains some text that will help us test chunking. "
                    "We want to make sure that the chunker correctly handles "
                    "multiple segments and creates appropriate chunks.",
                    "start": float(i * 5),
                    "duration": 5.0,
                }
            )
        return segments

    def test_chunker_initialization(self) -> None:
        """Test chunker initializes with correct parameters."""
        chunker = TranscriptChunker(chunk_size=1000, chunk_overlap=200)

        assert chunker.chunk_size == 1000
        assert chunker.chunk_overlap == 200

    def test_chunker_overlap_validation(self) -> None:
        """Test that overlap must be less than chunk size."""
        with pytest.raises(ValueError, match="chunk_overlap.*must be less than"):
            TranscriptChunker(chunk_size=100, chunk_overlap=100)

        with pytest.raises(ValueError, match="chunk_overlap.*must be less than"):
            TranscriptChunker(chunk_size=100, chunk_overlap=150)

    def test_chunk_by_segments_creates_chunks(
        self, chunker: TranscriptChunker, sample_segments: list[dict[str, Any]]
    ) -> None:
        """Verify segments are grouped into chunks."""
        chunks = chunker.chunk_by_segments(sample_segments)

        assert len(chunks) > 0
        assert all(isinstance(c, TranscriptChunk) for c in chunks)

    def test_chunk_by_segments_preserves_timestamps(
        self, chunker: TranscriptChunker, sample_segments: list[dict[str, Any]]
    ) -> None:
        """Verify timestamps are preserved in chunks."""
        chunks = chunker.chunk_by_segments(sample_segments)

        assert chunks[0].start_time == 0.0
        assert all(c.start_time is not None for c in chunks)

    def test_chunk_by_segments_handles_empty_input(
        self, chunker: TranscriptChunker
    ) -> None:
        """Empty segments returns empty list."""
        assert chunker.chunk_by_segments([]) == []

    def test_chunk_by_segments_single_segment(
        self, chunker: TranscriptChunker
    ) -> None:
        """Single segment creates single chunk."""
        segments = [{"text": "Single segment text.", "start": 0.0, "duration": 5.0}]

        chunks = chunker.chunk_by_segments(segments)

        assert len(chunks) == 1
        assert chunks[0].text == "Single segment text."
        assert chunks[0].start_time == 0.0

    def test_chunk_by_segments_multiple_chunks(
        self, chunker: TranscriptChunker, long_segments: list[dict[str, Any]]
    ) -> None:
        """Long transcript creates multiple chunks."""
        chunks = chunker.chunk_by_segments(long_segments)

        assert len(chunks) > 1
        # Verify chunks have proper timestamps
        for chunk in chunks:
            assert chunk.start_time >= 0
            assert chunk.end_time is None or chunk.end_time > chunk.start_time

    def test_chunk_by_segments_respects_size_limit(
        self, chunker: TranscriptChunker, long_segments: list[dict[str, Any]]
    ) -> None:
        """Verify most chunks don't significantly exceed chunk_size."""
        chunks = chunker.chunk_by_segments(long_segments)

        # Allow some overflow due to sentence boundary preservation
        max_allowed = chunker.chunk_size + 200
        for chunk in chunks[:-1]:  # Last chunk may be smaller
            assert len(chunk.text) <= max_allowed

    def test_chunk_by_segments_preserves_segment_indices(
        self, chunker: TranscriptChunker, sample_segments: list[dict[str, Any]]
    ) -> None:
        """Verify segment indices are tracked in chunks."""
        chunks = chunker.chunk_by_segments(sample_segments)

        # At least first chunk should have segment indices
        assert len(chunks[0].segment_indices) > 0

    def test_chunk_by_text_creates_chunks(self, chunker: TranscriptChunker) -> None:
        """Text-based chunking works as fallback."""
        text = (
            "First sentence about Python. "
            "Second sentence about programming. "
            "Third sentence about learning."
        )

        chunks = chunker.chunk_by_text(text)

        assert len(chunks) > 0
        assert all(isinstance(c, TranscriptChunk) for c in chunks)

    def test_chunk_by_text_handles_empty_input(
        self, chunker: TranscriptChunker
    ) -> None:
        """Empty text returns empty list."""
        assert chunker.chunk_by_text("") == []
        assert chunker.chunk_by_text("   ") == []

    def test_chunk_by_text_single_sentence(self, chunker: TranscriptChunker) -> None:
        """Single short sentence creates single chunk."""
        text = "This is a simple sentence."

        chunks = chunker.chunk_by_text(text)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].start_time == 0.0

    def test_chunk_by_text_long_text(self, chunker: TranscriptChunker) -> None:
        """Long text creates multiple chunks."""
        # Create a long text that will require multiple chunks
        sentences = [f"This is sentence number {i}." for i in range(50)]
        text = " ".join(sentences)

        chunks = chunker.chunk_by_text(text)

        assert len(chunks) > 1

    def test_chunk_by_text_timestamps_are_zero(
        self, chunker: TranscriptChunker
    ) -> None:
        """Text-based chunks have zero timestamps."""
        text = "Some text content."

        chunks = chunker.chunk_by_text(text)

        assert chunks[0].start_time == 0.0
        assert chunks[0].end_time is None

    def test_find_sentence_boundary(self, chunker: TranscriptChunker) -> None:
        """Test sentence boundary detection."""
        text = "First sentence. Second sentence. Third sentence."

        # Find boundary near middle
        boundary = chunker._find_sentence_boundary(text, 20)

        # Should find one of the sentence boundaries
        assert boundary in [16, 33]  # After "sentence. "


class TestChunkResult:
    """Tests for ChunkResult class."""

    def test_chunk_result_creation(self) -> None:
        """Test ChunkResult initialization."""
        result = ChunkResult(
            text="Sample text",
            start_time=125.5,
            end_time=130.0,
            transcript_id="t1",
            video_id="v1",
            score=0.95,
        )

        assert result.text == "Sample text"
        assert result.start_time == 125.5
        assert result.end_time == 130.0
        assert result.transcript_id == "t1"
        assert result.video_id == "v1"
        assert result.score == 0.95

    def test_format_timestamp(self) -> None:
        """Test timestamp formatting as MM:SS."""
        result = ChunkResult(
            text="Test",
            start_time=125.5,  # 2:05
            end_time=130.0,
            transcript_id="t1",
            video_id="v1",
            score=0.95,
        )

        assert result.format_timestamp() == "02:05"

    def test_format_timestamp_zero(self) -> None:
        """Test timestamp formatting at video start."""
        result = ChunkResult(
            text="Test",
            start_time=0.0,
            end_time=5.0,
            transcript_id="t1",
            video_id="v1",
            score=0.95,
        )

        assert result.format_timestamp() == "00:00"

    def test_format_timestamp_long_video(self) -> None:
        """Test timestamp formatting for long videos."""
        result = ChunkResult(
            text="Test",
            start_time=3661.0,  # 61:01
            end_time=3700.0,
            transcript_id="t1",
            video_id="v1",
            score=0.95,
        )

        assert result.format_timestamp() == "61:01"

    def test_to_dict(self) -> None:
        """Test dictionary conversion."""
        result = ChunkResult(
            text="Sample text",
            start_time=60.0,
            end_time=65.0,
            transcript_id="t1",
            video_id="v1",
            score=0.5,
        )

        d = result.to_dict()

        assert d["text"] == "Sample text"
        assert d["start_time"] == 60.0
        assert d["end_time"] == 65.0
        assert d["transcript_id"] == "t1"
        assert d["video_id"] == "v1"
        assert d["score"] == 0.5
        assert d["timestamp"] == "01:00"

    def test_repr(self) -> None:
        """Test string representation."""
        result = ChunkResult(
            text="Test",
            start_time=90.0,
            end_time=95.0,
            transcript_id="abc123",
            video_id="v1",
            score=0.1234,
        )

        repr_str = repr(result)

        assert "abc123" in repr_str
        assert "01:30" in repr_str
        assert "0.1234" in repr_str


class TestTranscriptKnowledgeBase:
    """Tests for TranscriptKnowledgeBase class."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> AgentConfig:
        """Mock agent config for testing with temp directory."""
        return AgentConfig(
            openai_api_key="test-key",
            anthropic_api_key=None,
            default_llm_provider="openai",
            default_model="gpt-4o",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=10,
            chunk_size=500,
            chunk_overlap=100,
        )

    @pytest.fixture
    def sample_segments(self) -> list[dict[str, Any]]:
        """Sample transcript segments for testing."""
        return [
            {"text": "Hello and welcome to this video.", "start": 0.0, "duration": 3.0},
            {
                "text": "Today we discuss Python programming.",
                "start": 3.0,
                "duration": 2.5,
            },
            {"text": "Python is a great language.", "start": 5.5, "duration": 3.0},
        ]

    @pytest.fixture
    def mock_embedding_func(self) -> MagicMock:
        """Create a mock embedding function."""
        mock_func = MagicMock()
        mock_func.ndims.return_value = 1536
        mock_func.SourceField.return_value = None
        mock_func.VectorField.return_value = None
        return mock_func

    def test_knowledge_base_initialization(self, mock_config: AgentConfig) -> None:
        """Test knowledge base initializes correctly."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        assert kb.config == mock_config
        assert kb._db is None  # Lazy initialization
        assert kb._table is None

    def test_chunker_uses_config_settings(self, mock_config: AgentConfig) -> None:
        """Test that chunker uses config chunk settings."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        assert kb._chunker.chunk_size == mock_config.chunk_size
        assert kb._chunker.chunk_overlap == mock_config.chunk_overlap

    @patch("src.agents.knowledge.transcript_knowledge._create_embedding_function")
    def test_db_connection_lazy_init(
        self,
        mock_create_embedding: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Test database connection is created lazily."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        # Access db property
        db = kb.db

        assert db is not None
        assert kb._db is db  # Same instance

    def test_is_indexed_returns_false_for_empty_db(
        self, mock_config: AgentConfig
    ) -> None:
        """Test is_indexed returns False when table doesn't exist."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        assert kb.is_indexed("nonexistent-id") is False

    def test_get_chunk_count_returns_zero_for_empty_db(
        self, mock_config: AgentConfig
    ) -> None:
        """Test get_chunk_count returns 0 when table doesn't exist."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        assert kb.get_chunk_count() == 0
        assert kb.get_chunk_count("some-id") == 0

    def test_clear_returns_zero_for_empty_db(self, mock_config: AgentConfig) -> None:
        """Test clear returns 0 when table doesn't exist."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        assert kb.clear("nonexistent-id") == 0

    @patch("src.agents.knowledge.transcript_knowledge._create_embedding_function")
    def test_search_returns_empty_for_missing_table(
        self,
        mock_create_embedding: MagicMock,
        mock_config: AgentConfig,
    ) -> None:
        """Test search returns empty list when table doesn't exist."""
        kb = TranscriptKnowledgeBase(config=mock_config)

        results = kb.search("test query")

        assert results == []


@pytest.mark.integration
class TestTranscriptKnowledgeBaseIntegration:
    """
    Integration tests that require actual OpenAI API calls.

    These tests are skipped by default. Run with:
        pytest -m integration
    """

    @pytest.fixture
    def real_config(self, tmp_path: Path) -> AgentConfig:
        """Create config with real API key from environment or .env file."""
        import os

        api_key = os.environ.get("OPENAI_API_KEY")

        # Try loading from .env file if not in environment
        if not api_key:
            try:
                from src.config import settings

                api_key = settings.openai_api_key
            except Exception:
                pass

        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        return AgentConfig(
            openai_api_key=api_key,
            anthropic_api_key=None,
            default_llm_provider="openai",
            default_model="gpt-4o",
            embedding_model="text-embedding-3-small",
            lancedb_uri=str(tmp_path / "lancedb"),
            max_context_chunks=10,
            chunk_size=500,
            chunk_overlap=100,
        )

    @pytest.fixture
    def sample_segments(self) -> list[dict[str, Any]]:
        """Sample transcript segments for testing."""
        return [
            {"text": "Welcome to our Python tutorial.", "start": 0.0, "duration": 3.0},
            {
                "text": "Today we will learn about functions.",
                "start": 3.0,
                "duration": 2.5,
            },
            {
                "text": "Functions are reusable blocks of code.",
                "start": 5.5,
                "duration": 3.0,
            },
            {
                "text": "They help organize your programs.",
                "start": 8.5,
                "duration": 2.5,
            },
        ]

    def test_load_and_search_transcript(
        self,
        real_config: AgentConfig,
        sample_segments: list[dict[str, Any]],
    ) -> None:
        """Test full workflow of loading and searching a transcript."""
        kb = TranscriptKnowledgeBase(config=real_config)

        # Load transcript
        transcript_text = " ".join(s["text"] for s in sample_segments)
        count = kb.load_transcript(
            transcript_id="test-123",
            transcript_text=transcript_text,
            transcript_segments=sample_segments,
            video_id="abc123",
        )

        assert count > 0
        assert kb.is_indexed("test-123")

        # Search
        results = kb.search("Python functions")

        assert len(results) > 0
        assert all(isinstance(r, ChunkResult) for r in results)
        assert all(r.transcript_id == "test-123" for r in results)

    def test_clear_removes_transcript(
        self,
        real_config: AgentConfig,
        sample_segments: list[dict[str, Any]],
    ) -> None:
        """Test that clear removes transcript chunks."""
        kb = TranscriptKnowledgeBase(config=real_config)

        # Load transcript
        transcript_text = " ".join(s["text"] for s in sample_segments)
        kb.load_transcript(
            transcript_id="test-456",
            transcript_text=transcript_text,
            transcript_segments=sample_segments,
            video_id="abc123",
        )

        assert kb.is_indexed("test-456")

        # Clear
        removed = kb.clear("test-456")

        assert removed > 0
        assert not kb.is_indexed("test-456")
