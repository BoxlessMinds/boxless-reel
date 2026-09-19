"""Setting SQLAlchemy model for storing user configuration."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Setting(Base):
    """SQLAlchemy model for user-configurable settings.

    Stores key-value pairs for LLM configuration, with optional encryption
    for sensitive values like API keys. Settings are scoped per-user.
    """

    __tablename__ = "settings"
    __table_args__ = (
        # Unique constraint: one setting per key per user
        UniqueConstraint("user_id", "key", name="uq_user_setting_key"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "llm", "embedding", "agent"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="settings"
    )

    def __repr__(self) -> str:
        """Return string representation of the setting."""
        return f"<Setting(key={self.key}, category={self.category})>"
