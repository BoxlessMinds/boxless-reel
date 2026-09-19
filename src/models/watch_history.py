"""SQLAlchemy models for imported Google Takeout watch history.

`WatchHistoryImport` / `WatchHistoryEntry` back the purge
of already-watched playlist items -- "watched" status isn't exposed by the
YouTube Data API at all, so this is populated entirely from an out-of-band
Takeout `watch-history.json` upload rather than any API read.

A user is expected to re-upload a newer Takeout export periodically, so
uploading again creates an *additional* `WatchHistoryImport` row rather than
replacing a prior one -- `WatchHistoryRepository.list_watched_video_ids`
reads the union of every import's entries, never just the latest, so no
history is lost or duplicated across re-uploads.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class WatchHistoryImport(Base):
    """One uploaded Google Takeout `watch-history.json` file.

    `status` tracks parsing progress through the upload, mirroring
    `Plan.STATUSES`'s convention of a small closed set of string states
    rather than a boolean flag, since Takeout parsing can fail outright
    (unreadable JSON) as well as succeed.
    """

    __tablename__ = "watch_history_imports"

    STATUSES = ("pending", "processing", "completed", "failed")

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "pending" | "processing" | "completed" | "failed"
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    entries: Mapped[list["WatchHistoryEntry"]] = relationship(
        "WatchHistoryEntry",
        back_populates="import_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return string representation of the watch history import."""
        return (
            f"<WatchHistoryImport(id={self.id}, "
            f"filename={self.original_filename!r}, status={self.status!r})>"
        )


class WatchHistoryEntry(Base):
    """A single parsed row from a Takeout `watch-history.json` import.

    `video_id` is nullable: some Takeout rows are ads or otherwise
    unparseable and are still stored (with `video_id=None`) so the parent
    import's `entry_count` matches what Takeout itself reported, rather
    than silently dropping rows. Such entries simply never match anything
    in `WatchHistoryRepository.list_watched_video_ids`'s join.

    No `updated_at` -- entries are bulk-inserted once at import time and
    never mutated afterward, the same immutable-child-row shape as
    `RefreshToken`.
    """

    __tablename__ = "watch_history_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    import_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("watch_history_imports.id"), nullable=False, index=True
    )
    video_id: Mapped[str | None] = mapped_column(String(11), nullable=True, index=True)
    watched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    import_record: Mapped["WatchHistoryImport"] = relationship(
        "WatchHistoryImport", back_populates="entries"
    )

    def __repr__(self) -> str:
        """Return string representation of the watch history entry."""
        return (
            f"<WatchHistoryEntry(id={self.id}, video_id={self.video_id}, "
            f"watched_at={self.watched_at})>"
        )
