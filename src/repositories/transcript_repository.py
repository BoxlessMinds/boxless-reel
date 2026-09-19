"""Repository for transcript database operations."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from src.models.transcript import Transcript

logger = logging.getLogger(__name__)


class TranscriptRepository:
    """Data access layer for transcript operations."""

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(self, transcript: Transcript) -> Transcript:
        """
        Create a new transcript record.

        Args:
            transcript: Transcript model instance to persist.

        Returns:
            The persisted transcript with generated ID.
        """
        logger.debug("Creating transcript for video_id: %s", transcript.video_id)
        self.db.add(transcript)
        self.db.commit()
        self.db.refresh(transcript)
        logger.debug("Created transcript with id: %s", transcript.id)
        return transcript

    def get_by_id(
        self,
        transcript_id: UUID | str,
        user_id: str | None = None,
    ) -> Transcript | None:
        """
        Get a transcript by its ID.

        Args:
            transcript_id: UUID of the transcript.
            user_id: Optional user ID to filter by ownership.

        Returns:
            Transcript if found, None otherwise.
        """
        logger.debug("Fetching transcript by id: %s (user_id=%s)", transcript_id, user_id)
        stmt = select(Transcript).where(Transcript.id == str(transcript_id))
        if user_id:
            stmt = stmt.where(Transcript.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Transcript not found: %s", transcript_id)
        return result

    def get_by_video_id(
        self,
        video_id: str,
        user_id: str | None = None,
    ) -> Transcript | None:
        """
        Get a transcript by YouTube video ID.

        Args:
            video_id: YouTube video ID (11 characters).
            user_id: Optional user ID to filter by ownership.

        Returns:
            Transcript if found, None otherwise.
        """
        logger.debug("Fetching transcript by video_id: %s (user_id=%s)", video_id, user_id)
        stmt = select(Transcript).where(Transcript.video_id == video_id)
        if user_id:
            stmt = stmt.where(Transcript.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Transcript not found for video_id: %s", video_id)
        return result

    def list_all(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        language: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Transcript]:
        """
        List transcripts with filtering and pagination.

        Args:
            user_id: User ID to filter by ownership.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            search: Search term for title and transcript_text (case-insensitive).
            language: Filter by language code.
            start_date: Filter by created_at >= start_date.
            end_date: Filter by created_at <= end_date.

        Returns:
            List of matching transcripts.
        """
        logger.debug(
            "Listing transcripts (user_id=%s, skip=%d, limit=%d, search=%s, language=%s)",
            user_id, skip, limit, search, language
        )
        stmt = select(Transcript).where(Transcript.user_id == user_id)
        stmt = self._apply_filters(stmt, search, language, start_date, end_date)
        stmt = stmt.order_by(Transcript.created_at.desc()).offset(skip).limit(limit)
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d transcripts", len(results))
        return results

    def count(
        self,
        user_id: str,
        search: str | None = None,
        language: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        """
        Count transcripts matching the filters.

        Args:
            user_id: User ID to filter by ownership.
            search: Search term for title and transcript_text (case-insensitive).
            language: Filter by language code.
            start_date: Filter by created_at >= start_date.
            end_date: Filter by created_at <= end_date.

        Returns:
            Count of matching transcripts.
        """
        logger.debug("Counting transcripts (user_id=%s, search=%s, language=%s)", user_id, search, language)
        stmt = select(func.count()).select_from(Transcript).where(Transcript.user_id == user_id)
        stmt = self._apply_filters(stmt, search, language, start_date, end_date)
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Count result: %d", count)
        return count

    def delete(self, transcript_id: UUID | str, user_id: str | None = None) -> bool:
        """
        Delete a transcript by ID.

        Args:
            transcript_id: UUID of the transcript to delete.
            user_id: Optional user ID to verify ownership.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting transcript: %s (user_id=%s)", transcript_id, user_id)
        transcript = self.get_by_id(transcript_id, user_id)
        if transcript is None:
            logger.debug("Transcript not found for deletion: %s", transcript_id)
            return False
        self.db.delete(transcript)
        self.db.commit()
        logger.debug("Deleted transcript: %s", transcript_id)
        return True

    def _apply_filters(
        self,
        stmt: Select,
        search: str | None,
        language: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> Select:
        """
        Apply common filters to a select statement.

        Args:
            stmt: SQLAlchemy select statement.
            search: Search term for title and transcript_text.
            language: Filter by language code.
            start_date: Filter by created_at >= start_date.
            end_date: Filter by created_at <= end_date.

        Returns:
            Modified select statement with filters applied.
        """
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Transcript.title.ilike(search_pattern),
                    Transcript.transcript_text.ilike(search_pattern),
                )
            )
        if language:
            stmt = stmt.where(Transcript.language == language)
        if start_date:
            stmt = stmt.where(Transcript.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Transcript.created_at <= end_date)
        return stmt
