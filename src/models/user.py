"""User SQLAlchemy model for authentication and authorization."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class User(Base):
    """SQLAlchemy model for user accounts.

    Supports invitation-only registration with role-based access control.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )  # "admin" | "user"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    invited_by: Mapped["User | None"] = relationship(
        "User", remote_side=[id], foreign_keys=[invited_by_id]
    )
    transcripts: Mapped[list["Transcript"]] = relationship(  # noqa: F821
        "Transcript", back_populates="owner", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="owner", cascade="all, delete-orphan"
    )
    settings: Mapped[list["Setting"]] = relationship(  # noqa: F821
        "Setting", back_populates="owner", cascade="all, delete-orphan"
    )
    invitations_sent: Mapped[list["Invitation"]] = relationship(  # noqa: F821
        "Invitation",
        back_populates="invited_by",
        foreign_keys="Invitation.invited_by_id",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # noqa: F821
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document", back_populates="owner", cascade="all, delete-orphan"
    )
    cross_chat_sessions: Mapped[list["CrossChatSession"]] = relationship(  # noqa: F821
        "CrossChatSession", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return string representation of the user."""
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
