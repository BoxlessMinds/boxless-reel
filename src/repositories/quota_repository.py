"""Repository for quota ledger database operations."""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.playlist import QuotaLedgerEntry

logger = logging.getLogger(__name__)


class QuotaRepository:
    """Data access layer for the append-only quota ledger."""

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(self, entry: QuotaLedgerEntry) -> QuotaLedgerEntry:
        """
        Persist a new quota ledger entry.

        Ledger rows are append-only — there is no update method, matching
        `QuotaLedgerEntry`'s "no `updated_at`, rows are never mutated in
        place" contract.

        Args:
            entry: QuotaLedgerEntry model instance to persist.

        Returns:
            The persisted entry with generated ID.
        """
        logger.debug(
            "Recording quota ledger entry (user_id=%s, endpoint=%s, units=%d)",
            entry.user_id, entry.endpoint, entry.units,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        logger.debug("Recorded quota ledger entry with id: %s", entry.id)
        return entry

    def get_units_used_since(
        self,
        start_utc: datetime,
        end_utc: datetime | None = None,
    ) -> int:
        """
        Sum quota units spent by all users within a UTC datetime window.

        This is a global aggregate, not scoped to a single user — the
        YouTube Data API quota pool is shared across the whole app.
        Pacific-day boundary computation (`zoneinfo`, midnight Pacific)
        is the caller's (`quota_service`) responsibility; this method only
        accepts already-converted UTC bounds and runs the SUM.

        Args:
            start_utc: Inclusive UTC start of the window.
            end_utc: Exclusive UTC end of the window. None means "through now".

        Returns:
            Sum of `QuotaLedgerEntry.units` across all users with
            `created_at` in `[start_utc, end_utc)`. Zero if no rows match.
        """
        logger.debug(
            "Summing quota units used since %s (end=%s)", start_utc, end_utc
        )
        stmt = select(func.coalesce(func.sum(QuotaLedgerEntry.units), 0)).where(
            QuotaLedgerEntry.created_at >= start_utc
        )
        if end_utc is not None:
            stmt = stmt.where(QuotaLedgerEntry.created_at < end_utc)
        result = self.db.execute(stmt).scalar()
        total = result or 0
        logger.debug("Units used in window: %d", total)
        return total
