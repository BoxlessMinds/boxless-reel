"""Tests for QuotaService's Pacific-day daily quota math.

No `googleapiclient`/`YouTubeDataService` involved here — this is pure
database + Pacific-day window arithmetic. `now` is injected explicitly on
every call so these tests are deterministic regardless of host timezone.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from src.config import settings
from src.models.playlist import QuotaLedgerEntry
from src.models.user import User
from src.repositories.quota_repository import QuotaRepository
from src.services.quota_service import QuotaService, get_daily_quota_status

# A fixed instant during Pacific Standard Time (UTC-8, no DST ambiguity):
# 2026-01-15 12:00 Pacific == 2026-01-15 20:00 UTC. Midnight Pacific that
# same day is 2026-01-15 08:00 UTC.
FIXED_NOW_UTC = datetime(2026, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
MIDNIGHT_PACIFIC_AS_UTC = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)


def _entry(user_id: str, units: int, created_at: datetime) -> QuotaLedgerEntry:
    """Build a QuotaLedgerEntry with an explicit (non-default) created_at."""
    return QuotaLedgerEntry(
        user_id=user_id, endpoint="test.endpoint", units=units, created_at=created_at
    )


class TestGetDailyQuotaStatus:
    """AC5: the global daily quota reflects all users' usage, Pacific-windowed."""

    def test_sums_multiple_users_within_pacific_window_excludes_outside(
        self, test_db: Session, test_user: User, test_admin: User
    ) -> None:
        inside_user1 = _entry(
            test_user.id, 100, MIDNIGHT_PACIFIC_AS_UTC.replace(tzinfo=None)
        )
        inside_user2 = _entry(
            test_admin.id, 250, FIXED_NOW_UTC.replace(tzinfo=None)
        )
        outside_before_midnight = _entry(
            test_user.id,
            9999,
            MIDNIGHT_PACIFIC_AS_UTC.replace(tzinfo=None).replace(hour=7),
        )
        test_db.add_all([inside_user1, inside_user2, outside_before_midnight])
        test_db.commit()

        status = get_daily_quota_status(test_db, now=FIXED_NOW_UTC)

        assert status.daily_limit == settings.youtube_daily_quota_limit
        assert status.used == 350
        assert status.remaining == settings.youtube_daily_quota_limit - 350

    def test_zero_usage_returns_full_remaining(self, test_db: Session) -> None:
        status = get_daily_quota_status(test_db, now=FIXED_NOW_UTC)

        assert status.used == 0
        assert status.remaining == settings.youtube_daily_quota_limit

    def test_instance_method_matches_module_function(
        self, test_db: Session, test_user: User
    ) -> None:
        test_db.add(_entry(test_user.id, 42, MIDNIGHT_PACIFIC_AS_UTC.replace(tzinfo=None)))
        test_db.commit()

        service = QuotaService(QuotaRepository(test_db))
        via_method = service.get_daily_quota_status(now=FIXED_NOW_UTC)
        via_function = get_daily_quota_status(test_db, now=FIXED_NOW_UTC)

        assert via_method == via_function == (
            settings.youtube_daily_quota_limit,
            42,
            settings.youtube_daily_quota_limit - 42,
        )

    def test_naive_now_is_treated_as_utc(
        self, test_db: Session, test_user: User
    ) -> None:
        test_db.add(_entry(test_user.id, 10, MIDNIGHT_PACIFIC_AS_UTC.replace(tzinfo=None)))
        test_db.commit()

        naive_now = FIXED_NOW_UTC.replace(tzinfo=None)
        status = get_daily_quota_status(test_db, now=naive_now)

        assert status.used == 10


@pytest.mark.parametrize("hour_utc,expected_used", [(7, 0), (8, 10)])
def test_pacific_midnight_boundary_is_inclusive(
    test_db: Session, test_user: User, hour_utc: int, expected_used: int
) -> None:
    """07:00 UTC is still the prior Pacific day; 08:00 UTC is the new one."""
    entry_time = MIDNIGHT_PACIFIC_AS_UTC.replace(tzinfo=None).replace(hour=hour_utc)
    test_db.add(_entry(test_user.id, 10, entry_time))
    test_db.commit()

    status = get_daily_quota_status(test_db, now=FIXED_NOW_UTC)

    assert status.used == expected_used
