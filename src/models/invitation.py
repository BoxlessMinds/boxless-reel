"""Invitation SQLAlchemy model for invitation-only registration."""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.utils.datetime_utils import as_utc


def generate_invitation_token() -> str:
    """Generate a secure, URL-safe invitation token."""
    return secrets.token_urlsafe(32)


class Invitation(Base):
    """SQLAlchemy model for user invitations.

    Invitations allow existing users to invite new users to register.
    Each invitation has a unique token that expires after a configurable period.
    """

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        default=generate_invitation_token
    )
    invited_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    registered_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "pending" | "accepted" | "expired" | "revoked"
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    invited_by: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="invitations_sent",
        foreign_keys=[invited_by_id]
    )
    registered_user: Mapped["User | None"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[registered_user_id]
    )

    def __repr__(self) -> str:
        """Return string representation of the invitation."""
        return f"<Invitation(id={self.id}, email={self.email}, status={self.status})>"

    @property
    def is_valid(self) -> bool:
        """Check if the invitation is still valid (pending and not expired)."""
        return self.status == "pending" and not self.is_expired

    @property
    def is_expired(self) -> bool:
        """Check if the invitation has expired (a stored naive value is treated as UTC)."""
        return datetime.now(timezone.utc) >= as_utc(self.expires_at)
