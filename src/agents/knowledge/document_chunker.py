"""Document chunking logic for semantic segmentation of uploaded documents."""

import re
from dataclasses import dataclass
from typing import Any

from src.utils.file_processing import ExtractedContent, ExtractedPage


@dataclass
class DocumentChunk:
    """
    A chunk of document text with associated page metadata.

    Attributes:
        text: The chunked document text content.
        chunk_index: Index of this chunk in the sequence.
        page_number: Page number this chunk starts on (None for non-paged docs).
        document_id: ID of the source document.
    """

    text: str
    chunk_index: int
    page_number: int | None = None
    document_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk to dictionary for storage."""
        return {
            "text": self.text,
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "document_id": self.document_id,
        }


class DocumentChunker:
    """
    Smart chunking for uploaded documents that preserves semantic coherence.

    Chunking strategies:
    1. Page-aware (for PDFs): Groups content by pages while respecting
       chunk size limits and sentence boundaries.
    2. Text-based (for DOCX/TXT/MD): Splits plain text on sentence
       boundaries with configurable overlap.

    Attributes:
        chunk_size: Target size for each chunk in characters (default: 1000).
        chunk_overlap: Number of characters to overlap between chunks (default: 200).
    """

    # Sentence boundary pattern - matches ., !, ? followed by space or end
    SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        """
        Initialize the chunker with configurable parameters.

        Args:
            chunk_size: Target chunk size in characters.
            chunk_overlap: Overlap between consecutive chunks.

        Raises:
            ValueError: If chunk_overlap >= chunk_size.
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than "
                f"chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(
        self,
        content: ExtractedContent,
        document_id: str | None = None,
    ) -> list[DocumentChunk]:
        """
        Chunk extracted document content.

        Automatically selects the appropriate chunking strategy based on
        whether the content has page information.

        Args:
            content: ExtractedContent from file processing.
            document_id: Optional document ID to associate with chunks.

        Returns:
            List of DocumentChunk objects.
        """
        if content.pages:
            return self.chunk_by_pages(content.pages, document_id)
        return self.chunk_by_text(content.text, document_id)

    def chunk_by_pages(
        self,
        pages: list[ExtractedPage],
        document_id: str | None = None,
    ) -> list[DocumentChunk]:
        """
        Chunk document using page information (for PDFs).

        Groups content from consecutive pages into chunks that:
        - Respect the target chunk_size
        - Preserve sentence boundaries where possible
        - Maintain page number information for citations

        Args:
            pages: List of ExtractedPage objects.
            document_id: Optional document ID.

        Returns:
            List of DocumentChunk objects with page numbers.
        """
        if not pages:
            return []

        chunks: list[DocumentChunk] = []
        current_text = ""
        current_page = pages[0].page_number
        chunk_index = 0

        for page in pages:
            page_text = page.text.strip()
            if not page_text:
                continue

            # Check if adding this page would exceed chunk size
            potential_text = (
                current_text + "\n\n" + page_text if current_text else page_text
            )

            if len(potential_text) > self.chunk_size and current_text:
                # Need to split - first try to fit content into current chunk
                # Find a good split point respecting sentence boundaries
                split_pos = self._find_sentence_boundary(
                    current_text, len(current_text) - self.chunk_overlap
                )

                # Create chunk with text up to split point
                chunks.append(
                    DocumentChunk(
                        text=current_text[:split_pos].strip(),
                        chunk_index=chunk_index,
                        page_number=current_page,
                        document_id=document_id,
                    )
                )
                chunk_index += 1

                # Start new chunk with overlap
                overlap_start = max(0, split_pos - self.chunk_overlap)
                overlap_text = current_text[overlap_start:].strip()

                current_text = overlap_text + "\n\n" + page_text if overlap_text else page_text
                current_page = page.page_number
            else:
                # Add page to current chunk
                current_text = potential_text
                if not current_text or current_text == page_text:
                    current_page = page.page_number

        # Don't forget the last chunk
        if current_text.strip():
            chunks.append(
                DocumentChunk(
                    text=current_text.strip(),
                    chunk_index=chunk_index,
                    page_number=current_page,
                    document_id=document_id,
                )
            )

        return chunks

    def chunk_by_text(
        self,
        text: str,
        document_id: str | None = None,
    ) -> list[DocumentChunk]:
        """
        Chunk plain text when page information is unavailable.

        Falls back to sentence-boundary based chunking with overlap.
        Page numbers will be None.

        Args:
            text: Plain document text to chunk.
            document_id: Optional document ID.

        Returns:
            List of DocumentChunk objects (page_number will be None).
        """
        if not text or not text.strip():
            return []

        # Split into sentences
        sentences = self.SENTENCE_BOUNDARY.split(text.strip())
        if not sentences:
            return [
                DocumentChunk(
                    text=text.strip(),
                    chunk_index=0,
                    page_number=None,
                    document_id=document_id,
                )
            ]

        chunks: list[DocumentChunk] = []
        current_text = ""
        chunk_index = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            potential_text = (
                current_text + " " + sentence if current_text else sentence
            )

            if len(potential_text) > self.chunk_size and current_text:
                # Save current chunk
                chunks.append(
                    DocumentChunk(
                        text=current_text.strip(),
                        chunk_index=chunk_index,
                        page_number=None,
                        document_id=document_id,
                    )
                )
                chunk_index += 1

                # Start new chunk with overlap from end of previous
                overlap_start = max(0, len(current_text) - self.chunk_overlap)
                overlap_text = current_text[overlap_start:].strip()
                current_text = overlap_text + " " + sentence if overlap_text else sentence
            else:
                current_text = potential_text

        # Don't forget the last chunk
        if current_text.strip():
            chunks.append(
                DocumentChunk(
                    text=current_text.strip(),
                    chunk_index=chunk_index,
                    page_number=None,
                    document_id=document_id,
                )
            )

        return chunks

    def _find_sentence_boundary(
        self,
        text: str,
        target_pos: int,
        search_window: int = 100,
    ) -> int:
        """
        Find the nearest sentence boundary to target position.

        Searches for sentence-ending punctuation (., !, ?) near the target
        position and returns the position after the punctuation.

        Args:
            text: Text to search in.
            target_pos: Ideal split position.
            search_window: Characters to search before/after target.

        Returns:
            Position of the nearest sentence boundary, or target_pos if none found.
        """
        if target_pos <= 0:
            return len(text)

        if target_pos >= len(text):
            return len(text)

        # Define search range
        search_start = max(0, target_pos - search_window)
        search_end = min(len(text), target_pos + search_window)
        search_text = text[search_start:search_end]

        # Find all sentence boundaries in the search window
        boundaries: list[int] = []
        for match in re.finditer(r"[.!?]\s+", search_text):
            # Position in original text
            abs_pos = search_start + match.end()
            boundaries.append(abs_pos)

        if not boundaries:
            # No sentence boundary found, return target position
            return target_pos

        # Find the boundary closest to target
        closest = min(boundaries, key=lambda x: abs(x - target_pos))
        return closest
