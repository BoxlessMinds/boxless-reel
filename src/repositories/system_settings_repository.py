"""Repository for system-wide settings."""

import logging

from sqlalchemy.orm import Session

from src.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)


class SystemSettingsRepository:
    """Repository for system-wide setting operations."""

    def __init__(self, db: Session) -> None:
        """Initialize with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def get(self, key: str) -> str | None:
        """Get a system setting value by key.

        Args:
            key: Setting key.

        Returns:
            Setting value if found, None otherwise.
        """
        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting else None

    def set(self, key: str, value: str, updated_by_id: str | None = None) -> SystemSetting:
        """Create or update a system setting.

        Args:
            key: Setting key.
            value: Setting value.
            updated_by_id: UUID of the admin who made the change.

        Returns:
            The created or updated SystemSetting.
        """
        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()

        if setting:
            setting.value = value
            setting.updated_by_id = updated_by_id
        else:
            setting = SystemSetting(
                key=key,
                value=value,
                updated_by_id=updated_by_id,
            )
            self.db.add(setting)

        self.db.commit()
        self.db.refresh(setting)
        logger.info("System setting updated: %s = %s", key, value)
        return setting

    def get_all(self) -> dict[str, str]:
        """Get all system settings as a dictionary.

        Returns:
            Dictionary of key-value pairs.
        """
        settings = self.db.query(SystemSetting).all()
        return {s.key: s.value for s in settings}
