"""Datetime helpers shared across models."""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware datetime, treating naive values as UTC.

    SQLite stores ``DateTime`` columns without a timezone, so a value that was
    written as UTC-aware comes back naive once the row is reloaded. Python
    refuses to compare naive and aware datetimes, so expiry checks normalise
    the stored value with this helper first.

    Args:
        value: A naive or timezone-aware datetime.

    Returns:
        The same instant with a timezone attached. Aware values are unchanged.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
