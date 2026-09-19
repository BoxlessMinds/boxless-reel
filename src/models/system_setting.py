"""SystemSetting SQLAlchemy model for storing system-wide configuration."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SystemSetting(Base):
    """SQLAlchemy model for system-wide configuration settings.

    Stores key-value pairs for system configuration that can be
    managed by administrators. Unlike the per-user Setting model,
    these settings apply globally to the entire application.
    """

    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        """Return string representation of the system setting."""
        return f"<SystemSetting(key={self.key}, value={self.value})>"
