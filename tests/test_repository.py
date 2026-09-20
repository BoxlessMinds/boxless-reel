"""Tests for TranscriptRepository database operations."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from src.models.transcript import Transcript
from src.models.user import User
from src.repositories.transcript_repository import TranscriptRepository


class TestTranscriptRepository:
    """Tests for TranscriptRepository CRUD operations."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db: Session, test_user: User) -> None:
        """Set up test fixtures."""
        self.db = test_db
        self.user_id = test_user.id
        self.repo = TranscriptRepository(test_db)

    def test_create_transcript(self, sample_transcript_data: dict[str, Any]) -> None:
        """Test creating a new transcript."""
        sample_transcript_data["user_id"] = self.user_id
        transcript = Transcript(**sample_transcript_data)
        result = self.repo.create(transcript)

        assert result.id is not None
        assert result.video_id == sample_transcript_data["video_id"]
        assert result.title == sample_transcript_data["title"]
        assert result.channel_name == sample_transcript_data["channel_name"]
        assert result.transcript_text == sample_transcript_data["transcript_text"]
        assert result.language == sample_transcript_data["language"]
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_create_generates_uuid(self, sample_transcript_data: dict[str, Any]) -> None:
        """Test that create auto-generates a UUID for the transcript."""
        sample_transcript_data["user_id"] = self.user_id
        transcript = Transcript(**sample_transcript_data)
        result = self.repo.create(transcript)

        # UUID should be a 36-character string (with hyphens)
        assert len(result.id) == 36
        assert "-" in result.id

    def test_get_by_id_returns_transcript(self, existing_transcript: Transcript) -> None:
        """Test retrieving transcript by ID."""
        result = self.repo.get_by_id(existing_transcript.id)

        assert result is not None
        assert result.id == existing_transcript.id
        assert result.video_id == existing_transcript.video_id

    def test_get_by_id_returns_none_when_not_found(self) -> None:
        """Test that get_by_id returns None for non-existent ID."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        result = self.repo.get_by_id(fake_uuid)

        assert result is None

    def test_get_by_video_id_returns_transcript(self, existing_transcript: Transcript) -> None:
        """Test retrieving transcript by video ID."""
        result = self.repo.get_by_video_id(existing_transcript.video_id)

        assert result is not None
        assert result.video_id == existing_transcript.video_id
        assert result.id == existing_transcript.id

    def test_get_by_video_id_returns_none_when_not_found(self) -> None:
        """Test that get_by_video_id returns None for non-existent video ID."""
        result = self.repo.get_by_video_id("nonexistent")

        assert result is None

    def test_list_all_returns_all_transcripts(self, multiple_transcripts: list[Transcript]) -> None:
        """Test listing all transcripts without filters."""
        result = self.repo.list_all(self.user_id)

        assert len(result) == len(multiple_transcripts)

    def test_list_all_with_pagination(self, multiple_transcripts: list[Transcript]) -> None:
        """Test pagination with skip and limit."""
        # Get first page
        page1 = self.repo.list_all(self.user_id, skip=0, limit=2)
        assert len(page1) == 2

        # Get second page
        page2 = self.repo.list_all(self.user_id, skip=2, limit=2)
        assert len(page2) == 1

    def test_list_all_ordered_by_created_at_desc(self, multiple_transcripts: list[Transcript]) -> None:
        """Test that results are ordered by created_at descending."""
        result = self.repo.list_all(self.user_id)

        # Verify descending order (most recent first)
        for i in range(len(result) - 1):
            assert result[i].created_at >= result[i + 1].created_at

    def test_list_all_with_search_filter(self, multiple_transcripts: list[Transcript]) -> None:
        """Test search filter on title."""
        result = self.repo.list_all(self.user_id, search="Python")

        assert len(result) == 1
        assert "Python" in result[0].title

    def test_list_all_search_in_transcript_text(self, multiple_transcripts: list[Transcript]) -> None:
        """Test search filter in transcript text."""
        result = self.repo.list_all(self.user_id, search="JavaScript")

        assert len(result) == 1
        assert "JavaScript" in result[0].transcript_text

    def test_list_all_search_case_insensitive(self, multiple_transcripts: list[Transcript]) -> None:
        """Test that search is case-insensitive."""
        result = self.repo.list_all(self.user_id, search="python")

        assert len(result) == 1
        assert "Python" in result[0].title

    def test_list_all_with_language_filter(self, multiple_transcripts: list[Transcript]) -> None:
        """Test filtering by language."""
        result = self.repo.list_all(self.user_id, language="es")

        assert len(result) == 1
        assert result[0].language == "es"

    def test_list_all_with_date_range(self, existing_transcript: Transcript) -> None:
        """Test filtering by date range."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        result = self.repo.list_all(self.user_id, start_date=yesterday, end_date=tomorrow)

        assert len(result) == 1
        assert result[0].id == existing_transcript.id

    def test_list_all_date_filter_excludes_old(self, existing_transcript: Transcript) -> None:
        """Test that date filter excludes records outside range."""
        future = datetime.now(timezone.utc) + timedelta(days=10)

        result = self.repo.list_all(self.user_id, start_date=future)

        assert len(result) == 0

    def test_count_returns_total(self, multiple_transcripts: list[Transcript]) -> None:
        """Test count returns total number of transcripts."""
        result = self.repo.count(self.user_id)

        assert result == len(multiple_transcripts)

    def test_count_with_search_filter(self, multiple_transcripts: list[Transcript]) -> None:
        """Test count respects search filter."""
        result = self.repo.count(self.user_id, search="Python")

        assert result == 1

    def test_count_with_language_filter(self, multiple_transcripts: list[Transcript]) -> None:
        """Test count respects language filter."""
        result = self.repo.count(self.user_id, language="en")

        assert result == 2  # Two English transcripts

    def test_count_empty_database(self) -> None:
        """Test count returns 0 for empty database."""
        result = self.repo.count(self.user_id)

        assert result == 0

    def test_list_all_and_count_exclude_other_users(
        self,
        multiple_transcripts: list[Transcript],
        test_admin: User,
    ) -> None:
        """Test that another user sees none of this user's transcripts."""
        assert self.repo.list_all(test_admin.id) == []
        assert self.repo.count(test_admin.id) == 0

        # The owning user still sees them all.
        assert len(self.repo.list_all(self.user_id)) == len(multiple_transcripts)
        assert self.repo.count(self.user_id) == len(multiple_transcripts)

    def test_delete_removes_transcript(self, existing_transcript: Transcript) -> None:
        """Test deleting a transcript."""
        transcript_id = existing_transcript.id

        result = self.repo.delete(transcript_id)

        assert result is True
        assert self.repo.get_by_id(transcript_id) is None

    def test_delete_returns_false_when_not_found(self) -> None:
        """Test that delete returns False for non-existent ID."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"

        result = self.repo.delete(fake_uuid)

        assert result is False

    def test_transcript_segments_stored_as_json(self, sample_transcript_data: dict[str, Any]) -> None:
        """Test that transcript_segments are stored and retrieved correctly as JSON."""
        sample_transcript_data["user_id"] = self.user_id
        transcript = Transcript(**sample_transcript_data)
        created = self.repo.create(transcript)

        retrieved = self.repo.get_by_id(created.id)

        assert retrieved is not None
        assert isinstance(retrieved.transcript_segments, list)
        assert len(retrieved.transcript_segments) == 2
        assert retrieved.transcript_segments[0]["text"] == "This is a test"
        assert retrieved.transcript_segments[0]["start"] == 0.0
