"""
Knowledge base components for transcript and document querying.

This package provides:
- TranscriptChunker: Smart chunking respecting timestamps and sentences
- TranscriptKnowledgeBase: LanceDB-backed vector store for transcript semantic search
- DocumentChunker: Smart chunking for uploaded documents with page awareness
- DocumentKnowledgeBase: LanceDB-backed vector store for document semantic search
"""

from src.agents.knowledge.chunker import TranscriptChunk, TranscriptChunker
from src.agents.knowledge.document_chunker import DocumentChunk, DocumentChunker
from src.agents.knowledge.document_knowledge import (
    DocumentChunkResult,
    DocumentKnowledgeBase,
)
from src.agents.knowledge.exceptions import (
    ChunkingError,
    EmbeddingError,
    IndexingError,
    KnowledgeBaseError,
    SearchError,
)
from src.agents.knowledge.transcript_knowledge import (
    ChunkResult,
    TranscriptKnowledgeBase,
)

__all__ = [
    # Transcript Chunking
    "TranscriptChunk",
    "TranscriptChunker",
    # Document Chunking
    "DocumentChunk",
    "DocumentChunker",
    # Knowledge Bases
    "ChunkResult",
    "TranscriptKnowledgeBase",
    "DocumentChunkResult",
    "DocumentKnowledgeBase",
    # Exceptions
    "KnowledgeBaseError",
    "ChunkingError",
    "EmbeddingError",
    "IndexingError",
    "SearchError",
]
