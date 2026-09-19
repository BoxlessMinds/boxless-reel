"""Service for transcript business logic operations."""

import logging
from datetime import datetime
from typing import Optional

from src.models import Transcript
from src.repositories import TranscriptRepository
from src.services.exceptions import TranscriptAlreadyExistsError
from src.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)


class TranscriptService:
    """
    Service layer for transcript operations.

    Orchestrates YouTube extraction and database storage,
    handling duplicate detection and the full extraction workflow.
    """

    def __init__(
        self,
        repository: TranscriptRepository,
        youtube_service: YouTubeService,
    ) -> None:
        """
        Initialize the transcript service.

        Args:
            repository: Repository for database operations.
            youtube_service: Service for YouTube data extraction.
        """
        self.repository = repository
        self.youtube_service = youtube_service

    def extract_and_save(self, url_or_id: str, user_id: str) -> Transcript:
        """
        Extract transcript from YouTube and save to database.

        Args:
            url_or_id: YouTube URL or video ID.
            user_id: UUID of the user who owns this transcript.

        Returns:
            The created Transcript model instance.

        Raises:
            TranscriptAlreadyExistsError: If transcript already exists for this user's video.
            InvalidVideoIdError: If URL/ID format is invalid.
            VideoNotFoundError: If video is unavailable.
            TranscriptNotAvailableError: If no English transcript available.
            YouTubeServiceError: For other extraction failures.
        """
        # Extract video ID first to check for duplicates before making API calls
        video_id = self.youtube_service.extract_video_id(url_or_id)

        # Check for existing transcript for this user
        existing = self.repository.get_by_video_id(video_id, user_id=user_id)
        if existing:
            logger.info("Transcript already exists for video %s (user=%s)", video_id, user_id)
            raise TranscriptAlreadyExistsError(
                f"Transcript already exists for video {video_id}"
            )

        # Extract transcript and metadata from YouTube
        logger.info("Extracting transcript and metadata for video %s", video_id)
        data = self.youtube_service.extract_all(url_or_id)

        # Create transcript model
        transcript = Transcript(
            video_id=data["video_id"],
            user_id=user_id,
            title=data["title"],
            channel_name=data["channel_name"],
            thumbnail_url=data["thumbnail_url"],
            transcript_text=data["transcript_text"],
            transcript_segments=data["transcript_segments"],
            language=data["language"],
            duration_seconds=data["duration_seconds"],
            source=data.get("source", "captions"),
        )

        # Save to database
        saved_transcript = self.repository.create(transcript)
        logger.info(
            "Saved transcript %s for video %s (user=%s)", saved_transcript.id, video_id, user_id
        )

        return saved_transcript

    def get_transcript(self, transcript_id: str, user_id: str) -> Optional[Transcript]:
        """
        Get a transcript by its ID.

        Args:
            transcript_id: UUID of the transcript.
            user_id: UUID of the user who owns the transcript.

        Returns:
            Transcript if found and owned by user, None otherwise.
        """
        return self.repository.get_by_id(transcript_id, user_id=user_id)

    def get_transcript_by_video_id(self, video_id: str, user_id: str) -> Optional[Transcript]:
        """
        Get a transcript by YouTube video ID.

        Args:
            video_id: 11-character YouTube video ID.
            user_id: UUID of the user who owns the transcript.

        Returns:
            Transcript if found and owned by user, None otherwise.
        """
        return self.repository.get_by_video_id(video_id, user_id=user_id)

    def list_transcripts(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        language: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[list[Transcript], int]:
        """
        List transcripts for a user with filtering and pagination.

        Args:
            user_id: UUID of the user who owns the transcripts.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            search: Search term for title/channel/transcript text.
            language: Filter by language code.
            start_date: Filter by created_at >= start_date.
            end_date: Filter by created_at <= end_date.

        Returns:
            Tuple of (list of transcripts, total count).
        """
        transcripts = self.repository.list_all(
            user_id=user_id,
            skip=skip,
            limit=limit,
            search=search,
            language=language,
            start_date=start_date,
            end_date=end_date,
        )

        total = self.repository.count(
            user_id=user_id,
            search=search,
            language=language,
            start_date=start_date,
            end_date=end_date,
        )

        return transcripts, total

    def delete_transcript(self, transcript_id: str, user_id: str) -> bool:
        """
        Delete a transcript by its ID.

        Args:
            transcript_id: UUID of the transcript to delete.
            user_id: UUID of the user who owns the transcript.

        Returns:
            True if deleted, False if not found or not owned by user.
        """
        deleted = self.repository.delete(transcript_id, user_id=user_id)
        if deleted:
            logger.info("Deleted transcript %s (user=%s)", transcript_id, user_id)
        return deleted
