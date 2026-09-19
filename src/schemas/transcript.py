"""Pydantic schemas for transcript request/response validation."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Regex pattern for YouTube URL validation
# Supports: youtube.com/watch?v=, youtu.be/, with optional params
YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)([\w-]{11})"
)


class TranscriptSegment(BaseModel):
    """A single timestamped segment of a transcript."""

    text: str = Field(description="The text content of this segment")
    start: float = Field(description="Start time in seconds")
    duration: float = Field(description="Duration of this segment in seconds")


class TranscriptExtractRequest(BaseModel):
    """Request body for extracting a transcript from a YouTube video."""

    youtube_url: str = Field(
        description="The YouTube video URL to extract transcript from"
    )

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        """Validate that the URL is a valid YouTube URL format."""
        if not YOUTUBE_URL_PATTERN.match(v):
            raise ValueError(
                "Invalid YouTube URL format. Expected formats: "
                "https://www.youtube.com/watch?v=VIDEO_ID, "
                "https://www.youtube.com/shorts/VIDEO_ID, or "
                "https://youtu.be/VIDEO_ID"
            )
        return v


class TranscriptResponse(BaseModel):
    """Full transcript response with all details."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    video_id: str = Field(description="YouTube video ID (11 characters)")
    title: str = Field(description="Video title")
    channel_name: str | None = Field(default=None, description="Channel name")
    thumbnail_url: str | None = Field(default=None, description="Video thumbnail URL")
    transcript_text: str = Field(description="Full transcript as plain text")
    transcript_segments: list[TranscriptSegment] = Field(
        description="Timestamped transcript segments"
    )
    language: str = Field(description="Language code (e.g., 'en')")
    source: str = Field(default="captions", description="Transcript source: 'captions' or 'whisper'")
    duration_seconds: int | None = Field(
        default=None, description="Video duration in seconds"
    )
    created_at: datetime = Field(description="When the transcript was extracted")
    updated_at: datetime = Field(description="When the transcript was last updated")


class TranscriptListQuery(BaseModel):
    """Query parameters for listing transcripts."""

    search: str | None = Field(
        default=None, max_length=200, description="Search term for title or transcript content"
    )
    language: str | None = Field(
        default=None, description="Filter by language code (e.g., 'en')"
    )
    start_date: datetime | None = Field(
        default=None, description="Filter transcripts created on or after this date"
    )
    end_date: datetime | None = Field(
        default=None, description="Filter transcripts created on or before this date"
    )
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Number of items per page (1-100)"
    )


class TranscriptListItem(BaseModel):
    """Lightweight transcript item for list responses (metadata only)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    video_id: str = Field(description="YouTube video ID (11 characters)")
    title: str = Field(description="Video title")
    channel_name: str | None = Field(default=None, description="Channel name")
    thumbnail_url: str | None = Field(default=None, description="Video thumbnail URL")
    language: str = Field(description="Language code (e.g., 'en')")
    source: str = Field(default="captions", description="Transcript source: 'captions' or 'whisper'")
    duration_seconds: int | None = Field(
        default=None, description="Video duration in seconds"
    )
    created_at: datetime = Field(description="When the transcript was extracted")


class TranscriptListResponse(BaseModel):
    """Paginated list response for transcripts."""

    items: list[TranscriptListItem] = Field(description="List of transcripts")
    total: int = Field(description="Total number of matching transcripts")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")
