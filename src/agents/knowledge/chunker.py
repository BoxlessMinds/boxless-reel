"""Transcript chunking logic for semantic segmentation."""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class TranscriptChunk:
    """
    A chunk of transcript text with associated timestamp metadata.

    Attributes:
        text: The chunked transcript text content.
        start_time: Start timestamp in seconds from video beginning.
        end_time: End timestamp in seconds (None if unknown).
        segment_indices: Original segment indices that comprise this chunk.
    """

    text: str
    start_time: float
    end_time: float | None = None
    segment_indices: tuple[int, ...] = ()

    @property
    def duration(self) -> float | None:
        """Calculate chunk duration if end_time is known."""
        if self.end_time is not None:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk to dictionary for storage."""
        return {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class TranscriptChunker:
    """
    Smart chunking for YouTube transcripts that preserves semantic coherence.

    Chunking strategies:
    1. Segment-based (preferred): Groups YouTube timestamp segments respecting
       sentence boundaries and chunk size limits.
    2. Text-based (fallback): Splits plain text on sentence boundaries with
       configurable overlap.

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

    def chunk_by_segments(
        self,
        segments: list[dict[str, Any]],
    ) -> list[TranscriptChunk]:
        """
        Chunk transcript using YouTube timestamp segments.

        Groups consecutive segments into chunks that:
        - Respect the target chunk_size
        - Preserve sentence boundaries where possible
        - Maintain timestamp information for citations

        Args:
            segments: List of segments with structure:
                [{"text": str, "start": float, "duration": float}, ...]

        Returns:
            List of TranscriptChunk objects with preserved timestamps.
        """
        if not segments:
            return []

        chunks: list[TranscriptChunk] = []
        current_text = ""
        current_start = segments[0].get("start", 0.0)
        current_indices: list[int] = []

        for idx, segment in enumerate(segments):
            segment_text = segment.get("text", "").strip()
            if not segment_text:
                continue

            # Check if adding this segment would exceed chunk size
            potential_text = (
                current_text + " " + segment_text if current_text else segment_text
            )

            if len(potential_text) > self.chunk_size and current_text:
                # Find a good split point respecting sentence boundaries
                split_pos = self._find_sentence_boundary(
                    current_text, len(current_text) - self.chunk_overlap
                )

                # Calculate end time for this chunk
                end_time = self._calculate_end_time(segments, current_indices)

                # Create chunk with text up to split point
                chunks.append(
                    TranscriptChunk(
                        text=current_text[:split_pos].strip(),
                        start_time=current_start,
                        end_time=end_time,
                        segment_indices=tuple(current_indices),
                    )
                )

                # Start new chunk with overlap
                overlap_start = max(0, split_pos - self.chunk_overlap)
                overlap_text = current_text[overlap_start:].strip()

                # Calculate new start time based on where overlap begins
                current_start = self._calculate_overlap_start_time(
                    segments, current_indices, overlap_start, len(current_text)
                )

                current_text = overlap_text + " " + segment_text
                current_indices = [idx]
            else:
                # Add segment to current chunk
                current_text = potential_text
                current_indices.append(idx)

        # Don't forget the last chunk
        if current_text.strip():
            end_time = self._calculate_end_time(segments, current_indices)
            chunks.append(
                TranscriptChunk(
                    text=current_text.strip(),
                    start_time=current_start,
                    end_time=end_time,
                    segment_indices=tuple(current_indices),
                )
            )

        return chunks

    def chunk_by_text(
        self,
        text: str,
    ) -> list[TranscriptChunk]:
        """
        Chunk plain text when segments are unavailable.

        Falls back to sentence-boundary based chunking with overlap.
        Timestamps are set to 0.0 since they're unknown.

        Args:
            text: Plain transcript text to chunk.

        Returns:
            List of TranscriptChunk objects (start_time will be 0.0).
        """
        if not text or not text.strip():
            return []

        # Split into sentences
        sentences = self.SENTENCE_BOUNDARY.split(text.strip())
        if not sentences:
            return [
                TranscriptChunk(
                    text=text.strip(),
                    start_time=0.0,
                    end_time=None,
                )
            ]

        chunks: list[TranscriptChunk] = []
        current_text = ""

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
                    TranscriptChunk(
                        text=current_text.strip(),
                        start_time=0.0,
                        end_time=None,
                    )
                )

                # Start new chunk with overlap from end of previous
                overlap_start = max(0, len(current_text) - self.chunk_overlap)
                overlap_text = current_text[overlap_start:].strip()
                current_text = overlap_text + " " + sentence if overlap_text else sentence
            else:
                current_text = potential_text

        # Don't forget the last chunk
        if current_text.strip():
            chunks.append(
                TranscriptChunk(
                    text=current_text.strip(),
                    start_time=0.0,
                    end_time=None,
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

    def _calculate_end_time(
        self,
        segments: list[dict[str, Any]],
        indices: list[int],
    ) -> float | None:
        """
        Calculate the end time for a chunk based on its segment indices.

        Args:
            segments: Full list of segments.
            indices: Indices of segments in this chunk.

        Returns:
            End time in seconds, or None if not determinable.
        """
        if not indices:
            return None

        last_idx = indices[-1]
        if last_idx >= len(segments):
            return None

        last_segment = segments[last_idx]
        start = last_segment.get("start", 0.0)
        duration = last_segment.get("duration", 0.0)

        return start + duration

    def _calculate_overlap_start_time(
        self,
        segments: list[dict[str, Any]],
        indices: list[int],
        overlap_char_start: int,
        total_text_len: int,
    ) -> float:
        """
        Estimate the start time for the overlap portion of a new chunk.

        Uses linear interpolation based on character position within
        the segments to estimate the timestamp.

        Args:
            segments: Full list of segments.
            indices: Indices of segments in the previous chunk.
            overlap_char_start: Character position where overlap starts.
            total_text_len: Total length of the previous chunk text.

        Returns:
            Estimated start time in seconds.
        """
        if not indices or total_text_len == 0:
            return 0.0

        # Calculate the fraction of text that corresponds to the overlap start
        fraction = overlap_char_start / total_text_len

        # Get the time range of the chunk
        first_segment = segments[indices[0]]
        last_segment = segments[indices[-1]]

        chunk_start = first_segment.get("start", 0.0)
        chunk_end = last_segment.get("start", 0.0) + last_segment.get("duration", 0.0)

        # Interpolate
        return chunk_start + fraction * (chunk_end - chunk_start)
