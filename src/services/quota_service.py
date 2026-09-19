"""Service for recording and reporting YouTube Data API quota usage.

Provides a minimal `record_read` helper so quota attribution
is recorded from the start, plus the daily
budget-status read used by `GET /quota` and the apply executor's budget
checks. The daily quota resets at midnight *Pacific* time, not UTC and not
host-local time, and is a single global pool shared across every app user
— it is never a per-user allowance.
"""

import logging
from datetime import datetime, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.config import settings
from src.models.playlist import QuotaLedgerEntry
from src.repositories.quota_repository import QuotaRepository

logger = logging.getLogger(__name__)

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


class DailyQuotaStatus(NamedTuple):
    """Snapshot of the shared, global YouTube Data API daily quota."""

    daily_limit: int
    used: int
    remaining: int


class QuotaService:
    """Service for recording YouTube Data API quota usage."""

    def __init__(self, quota_repository: QuotaRepository) -> None:
        """
        Initialize the service with its repository.

        Args:
            quota_repository: Repository for QuotaLedgerEntry persistence.
        """
        self.quota_repository = quota_repository

    def record_read(self, user_id: str, endpoint: str, units: int) -> QuotaLedgerEntry:
        """
        Record one read call's quota usage as a ledger entry.

        Args:
            user_id: The app user attributed with this usage (attribution
                only — quota enforcement is app-wide, not per-user, per the
                implementation plan's locked decisions).
            endpoint: The YouTube Data API endpoint called, e.g.
                "playlists.list" or "playlistItems.list".
            units: Quota units spent by this one call.

        Returns:
            The persisted QuotaLedgerEntry.
        """
        entry = QuotaLedgerEntry(user_id=user_id, endpoint=endpoint, units=units)
        recorded = self.quota_repository.create(entry)
        logger.debug(
            "Recorded %d quota unit(s) for user %s on %s", units, user_id, endpoint
        )
        return recorded

    def get_daily_quota_status(self, now: datetime | None = None) -> DailyQuotaStatus:
        """
        Compute the shared, global daily quota status for the current Pacific day.

        The daily quota window is midnight-to-midnight *Pacific* time
        (`America/Los_Angeles`), not UTC and not host-local time, matching
        the YouTube Data API's own reset schedule. Used/remaining are
        global sums across all users — this app has no per-user quota.

        Args:
            now: Optional injection point for "the current instant" (a
                timezone-aware, or UTC-naive, datetime). Lets tests pin the
                Pacific-day boundary deterministically regardless of host
                timezone. Defaults to the real current UTC time.

        Returns:
            A `DailyQuotaStatus` with the configured daily limit, units
            used so far today (Pacific), and units remaining (negative if
            usage has exceeded the limit).
        """
        current_utc = now if now is not None else datetime.now(timezone.utc)
        if current_utc.tzinfo is None:
            current_utc = current_utc.replace(tzinfo=timezone.utc)
        current_pacific = current_utc.astimezone(PACIFIC_TZ)
        midnight_pacific = current_pacific.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        midnight_pacific_as_utc = midnight_pacific.astimezone(timezone.utc).replace(
            tzinfo=None
        )
        used = self.quota_repository.get_units_used_since(midnight_pacific_as_utc)
        daily_limit = settings.youtube_daily_quota_limit
        logger.debug(
            "Daily quota status: limit=%d used=%d (since %s Pacific midnight)",
            daily_limit, used, midnight_pacific_as_utc,
        )
        return DailyQuotaStatus(
            daily_limit=daily_limit, used=used, remaining=daily_limit - used
        )


def get_quota_service(db: Session) -> QuotaService:
    """Factory function for QuotaService dependency injection."""
    repository = QuotaRepository(db)
    return QuotaService(repository)


def get_daily_quota_status(db: Session, now: datetime | None = None) -> DailyQuotaStatus:
    """
    Module-level convenience wrapper matching the story contract's exact shape.

    Equivalent to `get_quota_service(db).get_daily_quota_status(now=now)` —
    provided so a caller with only a `db: Session` in hand (e.g. a router
    dependency) doesn't need to construct a `QuotaService` itself.

    Args:
        db: Database session.
        now: See `QuotaService.get_daily_quota_status`.

    Returns:
        A `DailyQuotaStatus` for the current Pacific day.
    """
    return get_quota_service(db).get_daily_quota_status(now=now)
