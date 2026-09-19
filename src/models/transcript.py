"""Transcript SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Transcript(Base):
    """SQLAlchemy model for YouTube video transcripts."""

    __tablename__ = "transcripts"
    __table_args__ = (
        # Unique constraint: one transcript per video per user
        UniqueConstraint("user_id", "video_id", name="uq_user_video"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    video_id: Mapped[str] = mapped_column(
        String(11), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_segments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="captions")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="transcripts"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="transcript", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return string representation of the transcript."""
        return f"<Transcript(id={self.id}, video_id={self.video_id}, title={self.title!r})>"
