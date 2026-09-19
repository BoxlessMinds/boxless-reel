"""Repository for watch-history import and entry database operations."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.watch_history import WatchHistoryEntry, WatchHistoryImport

logger = logging.getLogger(__name__)


class WatchHistoryRepository:
    """Data access layer for watch-history import/entry operations."""

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    # -- WatchHistoryImport -----------------------------------------------

    def create_import(self, import_record: WatchHistoryImport) -> WatchHistoryImport:
        """
        Create a new watch-history import record.

        Args:
            import_record: WatchHistoryImport model instance to persist.

        Returns:
            The persisted import record with generated ID.
        """
        logger.debug(
            "Creating watch history import: %s", import_record.original_filename
        )
        self.db.add(import_record)
        self.db.commit()
        self.db.refresh(import_record)
        logger.debug("Created watch history import with id: %s", import_record.id)
        return import_record

    def get_import_by_id(
        self,
        import_id: str,
        user_id: str | None = None,
    ) -> WatchHistoryImport | None:
        """
        Get a watch-history import by its ID.

        Args:
            import_id: ID of the import record.
            user_id: Optional user ID to filter by ownership.

        Returns:
            WatchHistoryImport if found, None otherwise.
        """
        logger.debug(
            "Fetching watch history import by id: %s (user_id=%s)", import_id, user_id
        )
        stmt = select(WatchHistoryImport).where(WatchHistoryImport.id == import_id)
        if user_id:
            stmt = stmt.where(WatchHistoryImport.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Watch history import not found: %s", import_id)
        return result

    def list_imports(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[WatchHistoryImport]:
        """
        List a user's watch-history imports, most recent first.

        Args:
            user_id: User ID to filter by ownership.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of matching import records.
        """
        logger.debug(
            "Listing watch history imports (user_id=%s, skip=%d, limit=%d)",
            user_id, skip, limit,
        )
        stmt = (
            select(WatchHistoryImport)
            .where(WatchHistoryImport.user_id == user_id)
            .order_by(WatchHistoryImport.imported_at.desc())
            .offset(skip)
            .limit(limit)
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d watch history imports", len(results))
        return results

    def count_imports(self, user_id: str) -> int:
        """
        Count a user's watch-history imports.

        Args:
            user_id: User ID to filter by ownership.

        Returns:
            Count of matching import records.
        """
        logger.debug("Counting watch history imports (user_id=%s)", user_id)
        stmt = (
            select(func.count())
            .select_from(WatchHistoryImport)
            .where(WatchHistoryImport.user_id == user_id)
        )
        result = self.db.execute(stmt).scalar()
        return result or 0

    def update_import_status(
        self,
        import_id: str,
        status: str,
        **fields: Any,
    ) -> WatchHistoryImport | None:
        """
        Update a watch-history import's status and any accompanying fields.

        Args:
            import_id: ID of the import record.
            status: New status value -- one of `WatchHistoryImport.STATUSES`.
            **fields: Additional column values to set (e.g. `entry_count`,
                `imported_at`).

        Returns:
            The updated import record, or None if no record matches
            `import_id`.
        """
        logger.debug("Updating watch history import %s status -> %s", import_id, status)
        import_record = self.get_import_by_id(import_id)
        if import_record is None:
            logger.debug("Watch history import not found for status update: %s", import_id)
            return None
        import_record.status = status
        for key, value in fields.items():
            setattr(import_record, key, value)
        self.db.commit()
        self.db.refresh(import_record)
        return import_record

    # -- WatchHistoryEntry --------------------------------------------------

    def create_entries(
        self, entries: list[WatchHistoryEntry]
    ) -> list[WatchHistoryEntry]:
        """
        Persist a batch of watch-history entries in a single commit.

        Args:
            entries: WatchHistoryEntry model instances to persist,
                typically all belonging to the same import.

        Returns:
            The persisted entries with generated IDs, in the order given.
        """
        logger.debug("Creating %d watch history entries", len(entries))
        self.db.add_all(entries)
        self.db.commit()
        for entry in entries:
            self.db.refresh(entry)
        logger.debug("Created %d watch history entries", len(entries))
        return entries

    def list_watched_video_ids(
        self,
        user_id: str,
        watched_before: datetime | None = None,
    ) -> set[str]:
        """
        Return the set of distinct video_ids a user has watched, across the
        UNION of all of their watch-history imports.

        Joins across every `WatchHistoryImport` row owned by `user_id` --
        never just the most recent one -- so a purge plan generated after a
        newer Takeout export is re-uploaded still sees history from every
        prior import. Rows with `video_id IS NULL` (unparseable/ad Takeout
        entries) are excluded, since they can never match a playlist item.

        Args:
            user_id: The app user whose watch history to read.
            watched_before: If given, only counts a video as "watched" when
                it has at least one entry with `watched_at` strictly before
                this timestamp. If None, any watch entry at all qualifies.

        Returns:
            A set of YouTube video IDs the user has watched (optionally
            narrowed to before `watched_before`).
        """
        logger.debug(
            "Listing watched video_ids (user_id=%s, watched_before=%s)",
            user_id, watched_before,
        )
        stmt = (
            select(WatchHistoryEntry.video_id)
            .join(
                WatchHistoryImport,
                WatchHistoryEntry.import_id == WatchHistoryImport.id,
            )
            .where(
                WatchHistoryImport.user_id == user_id,
                WatchHistoryEntry.video_id.is_not(None),
            )
            .distinct()
        )
        if watched_before is not None:
            stmt = stmt.where(WatchHistoryEntry.watched_at < watched_before)
        results = set(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d watched video_ids for user %s", len(results), user_id)
        return results
