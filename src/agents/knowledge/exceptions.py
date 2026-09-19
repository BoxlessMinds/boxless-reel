"""Exceptions for knowledge base operations."""


class KnowledgeBaseError(Exception):
    """Base exception for knowledge base errors."""

    pass


class ChunkingError(KnowledgeBaseError):
    """Error during transcript chunking."""

    pass


class EmbeddingError(KnowledgeBaseError):
    """Error generating embeddings."""

    pass


class IndexingError(KnowledgeBaseError):
    """Error indexing transcript into vector store."""

    pass


class SearchError(KnowledgeBaseError):
    """Error searching the knowledge base."""

    pass
