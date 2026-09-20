"""RefreshToken SQLAlchemy model for JWT refresh token management."""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.utils.datetime_utils import as_utc


def generate_refresh_token() -> str:
    """Generate a secure refresh token."""
    return secrets.token_urlsafe(32)


class RefreshToken(Base):
    """SQLAlchemy model for refresh tokens.

    Refresh tokens allow users to obtain new access tokens without re-authenticating.
    They can be revoked individually or all at once for a user.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationship
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="refresh_tokens"
    )

    def __repr__(self) -> str:
        """Return string representation of the refresh token."""
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.is_revoked})>"

    @property
    def is_revoked(self) -> bool:
        """Check if the token has been revoked."""
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired (a stored naive value is treated as UTC)."""
        return datetime.now(timezone.utc) >= as_utc(self.expires_at)

    @property
    def is_valid(self) -> bool:
        """Check if the token is still valid (not revoked and not expired)."""
        return not self.is_revoked and not self.is_expired
