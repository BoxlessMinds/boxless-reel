"""Transcript knowledge base with LanceDB vector storage."""

import logging
from typing import Any

import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector

from src.agents.config import AgentConfig, get_agent_config
from src.agents.knowledge.chunker import TranscriptChunker
from src.agents.knowledge.exceptions import IndexingError, SearchError

logger = logging.getLogger(__name__)


class ChunkResult:
    """
    Search result containing chunk data and relevance score.

    Attributes:
        text: The chunk text content.
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.
        transcript_id: Source transcript ID.
        video_id: YouTube video ID.
        score: Distance score from vector search (lower is more similar).
    """

    def __init__(
        self,
        text: str,
        start_time: float,
        end_time: float | None,
        transcript_id: str,
        video_id: str,
        score: float,
    ) -> None:
        """
        Initialize a chunk result.

        Args:
            text: The chunk text content.
            start_time: Start timestamp in seconds.
            end_time: End timestamp in seconds.
            transcript_id: Source transcript ID.
            video_id: YouTube video ID.
            score: Distance score from vector search.
        """
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
        self.transcript_id = transcript_id
        self.video_id = video_id
        self.score = score

    def format_timestamp(self) -> str:
        """
        Format start_time as MM:SS for citations.

        Returns:
            Formatted timestamp string.
        """
        minutes = int(self.start_time // 60)
        seconds = int(self.start_time % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "transcript_id": self.transcript_id,
            "video_id": self.video_id,
            "score": self.score,
            "timestamp": self.format_timestamp(),
        }

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ChunkResult(transcript_id={self.transcript_id!r}, "
            f"timestamp={self.format_timestamp()!r}, score={self.score:.4f})"
        )


def _create_embedding_function(model_name: str, api_key: str | None = None):
    """
    Create an OpenAI embedding function for LanceDB.

    Args:
        model_name: The embedding model name (e.g., 'text-embedding-3-small').
        api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.

    Returns:
        LanceDB embedding function instance.
    """
    import os

    # LanceDB reads API key from environment variable
    # Set it before creating the embedding function
    if api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = api_key

    registry = get_registry()
    return registry.get("openai").create(name=model_name)


def _create_chunk_model(embedding_func):
    """
    Factory to create LanceDB schema class with configured embedding function.

    Args:
        embedding_func: LanceDB embedding function instance.

    Returns:
        LanceModel class with vector field configured.
    """

    class TranscriptChunkModel(LanceModel):
        """LanceDB schema for transcript chunks with embeddings."""

        id: str  # Unique chunk ID: {transcript_id}_{chunk_index}
        transcript_id: str  # Foreign key to transcripts table
        text: str = embedding_func.SourceField()  # Source for embedding
        start_time: float  # Start timestamp in seconds
        end_time: float | None = None  # End timestamp (may be None)
        video_id: str  # YouTube video ID for reference
        vector: Vector(embedding_func.ndims()) = embedding_func.VectorField()

    return TranscriptChunkModel


class TranscriptKnowledgeBase:
    """
    Knowledge base for transcript retrieval using LanceDB vectors.

    Provides:
    - Loading transcripts from database and chunking
    - Storing embeddings in LanceDB for semantic search
    - Retrieval methods for agent queries with timestamp citations

    Usage:
        kb = TranscriptKnowledgeBase()
        kb.load_transcript(
            transcript_id="abc123",
            transcript_text="Full transcript...",
            transcript_segments=[{"text": "...", "start": 0.0, "duration": 3.0}],
            video_id="dQw4w9WgXcQ"
        )
        results = kb.search("what does the speaker say about Python?")
    """

    TABLE_NAME = "transcript_chunks"

    def __init__(
        self,
        config: AgentConfig | None = None,
    ) -> None:
        """
        Initialize the knowledge base.

        Args:
            config: Agent configuration. Uses get_agent_config() if None.
        """
        self.config = config or get_agent_config()
        self._db: lancedb.DBConnection | None = None
        self._table: lancedb.table.Table | None = None
        self._embedding_func = None
        self._chunk_model = None
        self._chunker = TranscriptChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

    @property
    def db(self) -> lancedb.DBConnection:
        """
        Lazy initialization of LanceDB connection.

        Returns:
            LanceDB connection instance.
        """
        if self._db is None:
            self._db = lancedb.connect(self.config.lancedb_uri)
        return self._db

    @property
    def embedding_func(self):
        """
        Get or create the embedding function.

        Returns:
            LanceDB OpenAI embedding function.
        """
        if self._embedding_func is None:
            self._embedding_func = _create_embedding_function(
                self.config.embedding_model,
                self.config.openai_api_key,
            )
        return self._embedding_func

    @property
    def chunk_model(self):
        """
        Get or create the chunk model class with embedding function.

        Returns:
            LanceModel subclass for transcript chunks.
        """
        if self._chunk_model is None:
            self._chunk_model = _create_chunk_model(self.embedding_func)
        return self._chunk_model

    @property
    def table(self) -> lancedb.table.Table:
        """
        Get or create the LanceDB table.

        Returns:
            LanceDB table for transcript chunks.
        """
        if self._table is None:
            table_names = self.db.list_tables().tables
            if self.TABLE_NAME in table_names:
                self._table = self.db.open_table(self.TABLE_NAME)
            else:
                # Create empty table with schema
                self._table = self.db.create_table(
                    self.TABLE_NAME,
                    schema=self.chunk_model,
                )
        return self._table

    def load_transcript(
        self,
        transcript_id: str,
        transcript_text: str,
        transcript_segments: list[dict[str, Any]],
        video_id: str,
    ) -> int:
        """
        Load a transcript into the knowledge base.

        Chunks the transcript and stores embeddings in LanceDB.

        Args:
            transcript_id: UUID of the transcript.
            transcript_text: Full transcript text.
            transcript_segments: Timestamped segments from YouTube.
            video_id: YouTube video ID.

        Returns:
            Number of chunks created.

        Raises:
            IndexingError: If indexing fails.
        """
        logger.info("Loading transcript %s into knowledge base", transcript_id)

        # Remove existing chunks for this transcript (re-indexing)
        self.clear(transcript_id)

        # Chunk the transcript
        if transcript_segments:
            chunks = self._chunker.chunk_by_segments(transcript_segments)
        else:
            chunks = self._chunker.chunk_by_text(transcript_text)

        if not chunks:
            logger.warning("No chunks generated for transcript %s", transcript_id)
            return 0

        # Prepare data for LanceDB
        chunk_data = [
            {
                "id": f"{transcript_id}_{idx}",
                "transcript_id": transcript_id,
                "text": chunk.text,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "video_id": video_id,
            }
            for idx, chunk in enumerate(chunks)
        ]

        try:
            # Add to LanceDB (embeddings generated automatically)
            self.table.add(chunk_data)
        except Exception as e:
            logger.error("Failed to index transcript %s: %s", transcript_id, e)
            raise IndexingError(f"Failed to index transcript: {e}") from e

        logger.info(
            "Indexed %d chunks for transcript %s",
            len(chunks),
            transcript_id,
        )

        return len(chunks)

    def search(
        self,
        query: str,
        transcript_id: str | list[str] | None = None,
        num_results: int = 5,
    ) -> list[ChunkResult]:
        """
        Search for relevant transcript chunks.

        Args:
            query: Natural language search query.
            transcript_id: Optional filter - single transcript ID string,
                          list of transcript IDs, or None for all.
            num_results: Maximum number of results to return.

        Returns:
            List of ChunkResult objects ordered by relevance.

        Raises:
            SearchError: If search fails.
        """
        logger.debug("Searching knowledge base: %s", query[:50])

        # Check if table exists
        if self.TABLE_NAME not in self.db.list_tables().tables:
            logger.debug("Table does not exist, returning empty results")
            return []

        try:
            # Build search query
            search_query = self.table.search(query).limit(num_results)

            # Filter by transcript if specified
            if isinstance(transcript_id, list):
                # Multiple transcript IDs - use IN filter
                id_list = ",".join(repr(tid) for tid in transcript_id)
                search_query = search_query.where(
                    f"transcript_id IN ({id_list})"
                )
            elif transcript_id:
                search_query = search_query.where(
                    f"transcript_id = '{transcript_id}'"
                )

            # Execute search
            results = search_query.to_pandas()

            # Convert to ChunkResult objects
            chunk_results = []
            for _, row in results.iterrows():
                chunk_results.append(
                    ChunkResult(
                        text=row["text"],
                        start_time=row["start_time"],
                        end_time=row.get("end_time"),
                        transcript_id=row["transcript_id"],
                        video_id=row["video_id"],
                        score=row.get("_distance", 0.0),
                    )
                )

            return chunk_results

        except Exception as e:
            logger.error("Search failed: %s", e)
            raise SearchError(f"Failed to search knowledge base: {e}") from e

    def clear(self, transcript_id: str) -> int:
        """
        Remove all chunks for a transcript from the knowledge base.

        Args:
            transcript_id: UUID of the transcript to remove.

        Returns:
            Number of chunks removed.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return 0

        try:
            # Get count before deletion
            df = self.table.to_pandas()
            count = len(df[df["transcript_id"] == transcript_id])

            if count > 0:
                # Delete matching rows
                self.table.delete(f"transcript_id = '{transcript_id}'")
                logger.info(
                    "Removed %d chunks for transcript %s", count, transcript_id
                )

            return count

        except Exception as e:
            logger.warning("Failed to clear transcript %s: %s", transcript_id, e)
            return 0

    def is_indexed(self, transcript_id: str) -> bool:
        """
        Check if a transcript is already indexed.

        Args:
            transcript_id: UUID of the transcript.

        Returns:
            True if transcript has chunks in the knowledge base.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return False

        try:
            df = self.table.to_pandas()
            return len(df[df["transcript_id"] == transcript_id]) > 0
        except Exception:
            return False

    def get_chunk_count(self, transcript_id: str | None = None) -> int:
        """
        Get the number of indexed chunks.

        Args:
            transcript_id: Optional filter for specific transcript.

        Returns:
            Count of chunks in the knowledge base.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return 0

        try:
            df = self.table.to_pandas()

            if transcript_id:
                return len(df[df["transcript_id"] == transcript_id])

            return len(df)

        except Exception:
            return 0
