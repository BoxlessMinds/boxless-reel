"""SQLAlchemy models for the local YouTube playlist cache."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Playlist(Base):
    """SQLAlchemy model for a cached YouTube playlist.

    One row per (user, YouTube playlist), refreshed in place by
    ``PlaylistSyncService``. ``is_owned=False`` marks a public playlist cached
    on-demand as a future copy source rather than one of the
    connected user's own playlists.
    """

    __tablename__ = "playlists"
    __table_args__ = (
        UniqueConstraint("user_id", "youtube_playlist_id", name="uq_user_playlist"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    youtube_playlist_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_status: Mapped[str] = mapped_column(String(20), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_owned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    items: Mapped[list["PlaylistItem"]] = relationship(
        "PlaylistItem", back_populates="playlist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return string representation of the playlist."""
        return f"<Playlist(id={self.id}, youtube_playlist_id={self.youtube_playlist_id}, title={self.title!r})>"


class PlaylistItem(Base):
    """SQLAlchemy model for a single cached item within a playlist.

    Uniqueness is on ``(playlist_id, youtube_playlist_item_id)`` — deliberately
    **not** ``(playlist_id, video_id)`` — because a real YouTube playlist can
    contain the same video twice as two distinct items, which is exactly what
    dedupe needs to detect. Never add ``video_id`` to this
    constraint.
    """

    __tablename__ = "playlist_items"
    __table_args__ = (
        UniqueConstraint(
            "playlist_id", "youtube_playlist_item_id", name="uq_playlist_item"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    playlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("playlists.id"), nullable=False, index=True
    )
    youtube_playlist_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    video_id: Mapped[str] = mapped_column(String(11), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    channel_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    availability: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )  # "available" | "private" | "deleted" | "unknown"
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    added_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="items")

    def __repr__(self) -> str:
        """Return string representation of the playlist item."""
        return f"<PlaylistItem(id={self.id}, playlist_id={self.playlist_id}, video_id={self.video_id})>"


class QuotaLedgerEntry(Base):
    """Minimal append-only log of YouTube Data API quota units spent.

    Just enough for ``quota_service.record_read()`` to write a row per read
    call. Full ledger semantics (plan/op attribution, remaining-budget
    queries, Pacific-day windowing) are handled by ``QuotaService``, not this model.
    """

    __tablename__ = "quota_ledger_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        """Return string representation of the quota ledger entry."""
        return f"<QuotaLedgerEntry(id={self.id}, endpoint={self.endpoint}, units={self.units})>"
