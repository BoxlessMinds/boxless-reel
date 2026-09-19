"""Document knowledge base with LanceDB vector storage."""

import logging
from dataclasses import dataclass
from typing import Any

import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector

from src.agents.config import AgentConfig, get_agent_config
from src.agents.knowledge.document_chunker import DocumentChunk, DocumentChunker
from src.agents.knowledge.exceptions import IndexingError, SearchError
from src.utils.file_processing import ExtractedContent

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunkResult:
    """
    Search result containing document chunk data and relevance score.

    Attributes:
        text: The chunk text content.
        document_id: Source document ID.
        document_name: Original filename of the document.
        session_id: Session the document belongs to.
        page_number: Page number (if available).
        chunk_index: Index of the chunk in the document.
        score: Distance score from vector search (lower is more similar).
    """

    text: str
    document_id: str
    document_name: str
    session_id: str
    page_number: int | None
    chunk_index: int
    score: float

    def format_location(self) -> str:
        """
        Format page number or chunk index for citations.

        Returns:
            Formatted location string (e.g., "Page 5" or "Section 3").
        """
        if self.page_number is not None:
            return f"Page {self.page_number}"
        return f"Section {self.chunk_index + 1}"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "text": self.text,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "session_id": self.session_id,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "score": self.score,
            "location": self.format_location(),
        }

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"DocumentChunkResult(document_id={self.document_id!r}, "
            f"location={self.format_location()!r}, score={self.score:.4f})"
        )


def _create_document_embedding_function(model_name: str, api_key: str | None = None):
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


def _create_document_chunk_model(embedding_func):
    """
    Factory to create LanceDB schema class with configured embedding function.

    Args:
        embedding_func: LanceDB embedding function instance.

    Returns:
        LanceModel class with vector field configured.
    """

    class DocumentChunkModel(LanceModel):
        """LanceDB schema for document chunks with embeddings."""

        id: str  # Unique chunk ID: {document_id}_{chunk_index}
        document_id: str  # Foreign key to documents table
        session_id: str  # Session the document belongs to
        document_name: str  # Original filename
        text: str = embedding_func.SourceField()  # Source for embedding
        page_number: int | None = None  # Page number (PDFs only)
        chunk_index: int  # Index of this chunk
        vector: Vector(embedding_func.ndims()) = embedding_func.VectorField()

    return DocumentChunkModel


class DocumentKnowledgeBase:
    """
    Knowledge base for document retrieval using LanceDB vectors.

    Provides:
    - Indexing documents with text chunking and embeddings
    - Semantic search filtered by session_id
    - Document and session-level deletion

    Usage:
        kb = DocumentKnowledgeBase()
        kb.index_document(
            document_id="abc123",
            session_id="session456",
            document_name="report.pdf",
            content=extracted_content,
        )
        results = kb.search("quarterly revenue", session_id="session456")
    """

    TABLE_NAME = "document_chunks"

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
        self._chunker = DocumentChunker(
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
            self._embedding_func = _create_document_embedding_function(
                self.config.embedding_model,
                self.config.openai_api_key,
            )
        return self._embedding_func

    @property
    def chunk_model(self):
        """
        Get or create the chunk model class with embedding function.

        Returns:
            LanceModel subclass for document chunks.
        """
        if self._chunk_model is None:
            self._chunk_model = _create_document_chunk_model(self.embedding_func)
        return self._chunk_model

    @property
    def table(self) -> lancedb.table.Table:
        """
        Get or create the LanceDB table.

        Returns:
            LanceDB table for document chunks.
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

    def index_document(
        self,
        document_id: str,
        session_id: str,
        document_name: str,
        content: ExtractedContent,
    ) -> int:
        """
        Index a document into the knowledge base.

        Chunks the document and stores embeddings in LanceDB.

        Args:
            document_id: UUID of the document.
            session_id: UUID of the session.
            document_name: Original filename.
            content: Extracted content from the document.

        Returns:
            Number of chunks created.

        Raises:
            IndexingError: If indexing fails.
        """
        logger.info("Indexing document %s into knowledge base", document_id)

        # Remove existing chunks for this document (re-indexing)
        self.delete_document(document_id)

        # Chunk the document
        chunks = self._chunker.chunk_document(content, document_id)

        if not chunks:
            logger.warning("No chunks generated for document %s", document_id)
            return 0

        # Prepare data for LanceDB
        chunk_data = [
            {
                "id": f"{document_id}_{chunk.chunk_index}",
                "document_id": document_id,
                "session_id": session_id,
                "document_name": document_name,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ]

        try:
            # Add to LanceDB (embeddings generated automatically)
            self.table.add(chunk_data)
        except Exception as e:
            logger.error("Failed to index document %s: %s", document_id, e)
            raise IndexingError(f"Failed to index document: {e}") from e

        logger.info(
            "Indexed %d chunks for document %s",
            len(chunks),
            document_id,
        )

        return len(chunks)

    def search(
        self,
        query: str,
        session_id: str,
        num_results: int = 5,
    ) -> list[DocumentChunkResult]:
        """
        Search for relevant document chunks within a session.

        Args:
            query: Natural language search query.
            session_id: Filter to search within a specific session's documents.
            num_results: Maximum number of results to return.

        Returns:
            List of DocumentChunkResult objects ordered by relevance.

        Raises:
            SearchError: If search fails.
        """
        logger.debug("Searching document knowledge base: %s", query[:50])

        # Check if table exists
        if self.TABLE_NAME not in self.db.list_tables().tables:
            logger.debug("Document table does not exist, returning empty results")
            return []

        try:
            # Build search query with session filter
            search_query = (
                self.table.search(query)
                .where(f"session_id = '{session_id}'")
                .limit(num_results)
            )

            # Execute search
            results = search_query.to_pandas()

            # Convert to DocumentChunkResult objects
            chunk_results = []
            for _, row in results.iterrows():
                chunk_results.append(
                    DocumentChunkResult(
                        text=row["text"],
                        document_id=row["document_id"],
                        document_name=row["document_name"],
                        session_id=row["session_id"],
                        page_number=row.get("page_number"),
                        chunk_index=row["chunk_index"],
                        score=row.get("_distance", 0.0),
                    )
                )

            return chunk_results

        except Exception as e:
            logger.error("Document search failed: %s", e)
            raise SearchError(f"Failed to search document knowledge base: {e}") from e

    def delete_document(self, document_id: str) -> int:
        """
        Remove all chunks for a document from the knowledge base.

        Args:
            document_id: UUID of the document to remove.

        Returns:
            Number of chunks removed.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return 0

        try:
            # Get count before deletion
            df = self.table.to_pandas()
            count = len(df[df["document_id"] == document_id])

            if count > 0:
                # Delete matching rows
                self.table.delete(f"document_id = '{document_id}'")
                logger.info(
                    "Removed %d chunks for document %s", count, document_id
                )

            return count

        except Exception as e:
            logger.warning("Failed to delete document %s: %s", document_id, e)
            return 0

    def delete_session_documents(self, session_id: str) -> int:
        """
        Remove all document chunks for a session.

        Args:
            session_id: UUID of the session.

        Returns:
            Number of chunks removed.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return 0

        try:
            # Get count before deletion
            df = self.table.to_pandas()
            count = len(df[df["session_id"] == session_id])

            if count > 0:
                # Delete matching rows
                self.table.delete(f"session_id = '{session_id}'")
                logger.info(
                    "Removed %d chunks for session %s", count, session_id
                )

            return count

        except Exception as e:
            logger.warning("Failed to delete session documents %s: %s", session_id, e)
            return 0

    def is_indexed(self, document_id: str) -> bool:
        """
        Check if a document is already indexed.

        Args:
            document_id: UUID of the document.

        Returns:
            True if document has chunks in the knowledge base.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return False

        try:
            df = self.table.to_pandas()
            return len(df[df["document_id"] == document_id]) > 0
        except Exception:
            return False

    def get_chunk_count(
        self,
        document_id: str | None = None,
        session_id: str | None = None,
    ) -> int:
        """
        Get the number of indexed chunks.

        Args:
            document_id: Optional filter for specific document.
            session_id: Optional filter for specific session.

        Returns:
            Count of chunks in the knowledge base.
        """
        if self.TABLE_NAME not in self.db.list_tables().tables:
            return 0

        try:
            df = self.table.to_pandas()

            if document_id:
                df = df[df["document_id"] == document_id]
            if session_id:
                df = df[df["session_id"] == session_id]

            return len(df)

        except Exception:
            return 0
