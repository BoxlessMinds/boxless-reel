"""SQLAlchemy models for cross-chat sessions, references, and messages."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class CrossChatSession(Base):
    """SQLAlchemy model for cross-chat sessions that span multiple transcripts."""

    __tablename__ = "cross_chat_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="cross_chat_sessions"
    )
    referenced_sessions: Mapped[list["CrossChatSessionReference"]] = relationship(
        "CrossChatSessionReference",
        back_populates="cross_chat_session",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list["CrossChatMessage"]] = relationship(
        "CrossChatMessage",
        back_populates="cross_chat_session",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return string representation of the cross-chat session."""
        return (
            f"<CrossChatSession(id={self.id}, model={self.model_name}, "
            f"refs={len(self.referenced_sessions) if self.referenced_sessions else 0})>"
        )


class CrossChatSessionReference(Base):
    """SQLAlchemy model for linking cross-chat sessions to agent sessions."""

    __tablename__ = "cross_chat_session_references"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    cross_chat_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cross_chat_sessions.id"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    cross_chat_session: Mapped["CrossChatSession"] = relationship(
        "CrossChatSession", back_populates="referenced_sessions"
    )
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session",
    )

    def __repr__(self) -> str:
        """Return string representation of the cross-chat session reference."""
        return (
            f"<CrossChatSessionReference(id={self.id}, "
            f"cross_chat={self.cross_chat_session_id}, session={self.session_id})>"
        )


class CrossChatMessage(Base):
    """SQLAlchemy model for cross-chat session messages."""

    __tablename__ = "cross_chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    cross_chat_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cross_chat_sessions.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationship
    cross_chat_session: Mapped["CrossChatSession"] = relationship(
        "CrossChatSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        """Return string representation of the cross-chat message."""
        content_preview = (
            self.content[:50] + "..." if len(self.content) > 50 else self.content
        )
        return (
            f"<CrossChatMessage(id={self.id}, role={self.role}, "
            f"content={content_preview!r})>"
        )
