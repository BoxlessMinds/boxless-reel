"""Service for ingesting Google Takeout watch-history.json exports."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from src.config import settings
from src.models.watch_history import WatchHistoryEntry, WatchHistoryImport
from src.repositories.watch_history_repository import WatchHistoryRepository
from src.services.exceptions import InvalidVideoIdError
from src.utils.youtube_url_parser import extract_video_id

logger = logging.getLogger(__name__)

# Upload chunk size for streaming (1MB), matching document_service.py.
UPLOAD_CHUNK_SIZE = 1024 * 1024

# Takeout watch-history.json can run to tens of thousands of rows for
# long-time YouTube users; cap generously rather than tightly.
MAX_TAKEOUT_FILE_SIZE = 100 * 1024 * 1024


def _utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime (matches this repo's DateTime columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WatchHistoryServiceError(Exception):
    """Base exception for watch history service errors."""

    pass


class InvalidTakeoutFileError(WatchHistoryServiceError):
    """Raised when the uploaded file isn't a parseable Takeout watch-history.json."""

    pass


class TakeoutFileTooLargeError(WatchHistoryServiceError):
    """Raised when the uploaded file exceeds the size limit."""

    pass


class ParsedWatchHistoryRow(NamedTuple):
    """A single storable Takeout watch-history row.

    `video_id` is None for ad/unparseable rows (missing `titleUrl`, or a
    `titleUrl` that doesn't resolve to a video ID) -- these are still
    returned for persistence with `video_id=None`, matching
    `WatchHistoryEntry.video_id`'s nullable design so `entry_count` reflects
    Takeout's own row count rather than silently dropping ad rows.
    """

    video_id: str | None
    watched_at: datetime
    title: str


class WatchHistoryService:
    """
    Service layer for importing Google Takeout watch-history.json exports.

    Orchestrates:
    - Streaming upload to disk (mirrors DocumentService._stream_to_file)
    - Parsing/classifying Takeout rows (video entries vs. ads/unparseable)
    - Delegating persistence to WatchHistoryRepository

    No direct DB queries live here - all persistence goes through the
    injected WatchHistoryRepository.
    """

    def __init__(
        self,
        repository: WatchHistoryRepository,
        storage_path: Path | None = None,
    ) -> None:
        """
        Initialize the watch history service.

        Args:
            repository: Repository for watch history database operations.
            storage_path: Base path for storing uploaded Takeout files.
        """
        self.repository = repository
        self.storage_path = storage_path or Path(settings.watch_history_storage_path)

    async def import_watch_history(
        self,
        file: UploadFile,
        user_id: str,
    ) -> WatchHistoryImport:
        """
        Upload, parse, and persist a Google Takeout watch-history.json export.

        Streams the upload to disk, parses it as a Takeout JSON array, and
        classifies each row: a row with a resolvable `titleUrl` is stored
        with its video ID, a row without one (Takeout's ad/non-video rows)
        is still stored with `video_id=None`, and a row missing/malformed
        `title` or `time` is dropped outright. The whole import succeeds
        even when some or all rows are ads/unparseable - only a file that
        isn't valid JSON, or isn't a top-level array, fails.

        Args:
            file: Uploaded Takeout watch-history.json file.
            user_id: UUID of the user importing the file.

        Returns:
            The created WatchHistoryImport record.

        Raises:
            InvalidTakeoutFileError: If the file isn't valid JSON or isn't a
                top-level JSON array.
            TakeoutFileTooLargeError: If the file exceeds the size limit.
        """
        original_filename = file.filename or "watch-history.json"

        storage_dir = self.storage_path / user_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / f"{uuid4()}.json"

        await self._stream_to_file(file, file_path, MAX_TAKEOUT_FILE_SIZE)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_rows = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            file_path.unlink(missing_ok=True)
            logger.warning("Failed to parse Takeout upload %s: %s", original_filename, e)
            raise InvalidTakeoutFileError(f"'{original_filename}' is not valid JSON") from e

        if not isinstance(raw_rows, list):
            file_path.unlink(missing_ok=True)
            logger.warning(
                "Takeout upload %s is not a JSON array (got %s)",
                original_filename,
                type(raw_rows).__name__,
            )
            raise InvalidTakeoutFileError(
                f"'{original_filename}' is not a Takeout watch-history.json export "
                "(expected a top-level JSON array)"
            )

        parsed_rows, skipped_count = self._parse_entries(raw_rows)

        import_record = WatchHistoryImport(
            user_id=user_id,
            original_filename=original_filename,
            status="completed",
            entry_count=len(parsed_rows),
            imported_at=_utc_now_naive(),
        )
        import_record = self.repository.create_import(import_record)

        if parsed_rows:
            entries = [
                WatchHistoryEntry(
                    import_id=import_record.id,
                    video_id=row.video_id,
                    watched_at=row.watched_at,
                    title=row.title,
                )
                for row in parsed_rows
            ]
            self.repository.create_entries(entries)

        logger.info(
            "Imported watch history %s: %d entries stored, %d rows skipped",
            original_filename,
            len(parsed_rows),
            skipped_count,
        )

        return import_record

    def list_imports(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[WatchHistoryImport], int]:
        """
        List a user's watch-history imports, most recent first.

        Args:
            user_id: UUID of the user.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            Tuple of (imports list, total count).
        """
        imports = self.repository.list_imports(user_id, skip=skip, limit=limit)
        total = self.repository.count_imports(user_id)
        return imports, total

    async def _stream_to_file(
        self,
        file: UploadFile,
        destination: Path,
        max_size: int,
    ) -> int:
        """
        Stream uploaded file to disk with size validation.

        Args:
            file: Uploaded file from FastAPI.
            destination: Target path for the file.
            max_size: Maximum allowed size in bytes.

        Returns:
            Total file size in bytes.

        Raises:
            TakeoutFileTooLargeError: If file exceeds max_size.
        """
        total_size = 0

        with open(destination, "wb") as dest:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    dest.close()
                    destination.unlink()
                    max_mb = max_size / (1024 * 1024)
                    raise TakeoutFileTooLargeError(
                        f"File too large. Maximum size is {max_mb:.0f}MB"
                    )
                dest.write(chunk)

        return total_size

    def _parse_entries(self, raw_rows: list) -> tuple[list[ParsedWatchHistoryRow], int]:
        """
        Classify and parse the top-level rows of a Takeout watch-history.json.

        Args:
            raw_rows: Deserialized JSON array from the Takeout export.

        Returns:
            Tuple of (rows to persist, count of structurally-dropped rows).
        """
        entries: list[ParsedWatchHistoryRow] = []
        skipped_count = 0

        for raw_row in raw_rows:
            entry = self._parse_entry(raw_row)
            if entry is None:
                skipped_count += 1
            else:
                entries.append(entry)

        return entries, skipped_count

    def _parse_entry(self, raw_row: object) -> ParsedWatchHistoryRow | None:
        """
        Parse a single Takeout watch-history.json row.

        Returns None only when the row is structurally unusable (not a
        dict, or missing/unparseable `title`/`time` - WatchHistoryEntry
        requires both). A row with no `titleUrl` (Takeout's ad/non-video
        rows) or an unresolvable `titleUrl` is still returned, with
        `video_id=None`, so it is persisted and counted toward
        `entry_count` - matching Takeout's own row count.

        Args:
            raw_row: A single deserialized element from the Takeout array.

        Returns:
            A ParsedWatchHistoryRow, or None if the row must be dropped.
        """
        if not isinstance(raw_row, dict):
            return None

        title = raw_row.get("title")
        if not isinstance(title, str) or not title:
            return None

        watched_at = self._parse_timestamp(raw_row.get("time"))
        if watched_at is None:
            return None

        video_id: str | None = None
        title_url = raw_row.get("titleUrl")
        if isinstance(title_url, str) and title_url:
            try:
                video_id = extract_video_id(title_url)
            except InvalidVideoIdError:
                video_id = None

        return ParsedWatchHistoryRow(video_id=video_id, watched_at=watched_at, title=title)

    @staticmethod
    def _parse_timestamp(raw_time: object) -> datetime | None:
        """
        Parse a Takeout ISO-8601 timestamp string (e.g. "2024-01-01T00:00:00.000Z").

        Args:
            raw_time: The raw `time` field value from a Takeout row.

        Returns:
            A naive UTC datetime, or None if missing/unparseable.
        """
        if not isinstance(raw_time, str) or not raw_time:
            return None
        try:
            parsed = datetime.fromisoformat(raw_time)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed


def get_watch_history_service(db: Session) -> WatchHistoryService:
    """Factory function for WatchHistoryService dependency injection."""
    repository = WatchHistoryRepository(db)
    return WatchHistoryService(repository)
