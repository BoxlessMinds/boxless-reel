"""Repository for settings database operations."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.setting import Setting
from src.utils.encryption import SettingsEncryption, get_encryption

logger = logging.getLogger(__name__)


class SettingsRepository:
    """Data access layer for settings operations.

    Handles encryption/decryption of sensitive values transparently.
    """

    # Keys that contain sensitive data and should be encrypted
    SENSITIVE_KEYS: set[str] = {
        "llm.anthropic_api_key",
        "llm.openai_api_key",
    }

    # Mask to use for displaying sensitive values
    MASKED_VALUE = "••••••••"

    def __init__(
        self, db: Session, encryption: SettingsEncryption | None = None
    ) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
            encryption: Optional encryption instance. If not provided, uses singleton.
        """
        self.db = db
        self.encryption = encryption or get_encryption()

    def get(self, key: str, user_id: str) -> str | None:
        """
        Get a setting value by key for a specific user.

        Automatically decrypts sensitive values.

        Args:
            key: The setting key (e.g., "llm.anthropic_api_key").
            user_id: The user ID who owns the setting.

        Returns:
            The setting value (decrypted if sensitive), or None if not found.
        """
        logger.debug("Fetching setting: %s (user_id=%s)", key, user_id)
        stmt = select(Setting).where(Setting.key == key, Setting.user_id == user_id)
        setting = self.db.execute(stmt).scalar_one_or_none()

        if setting is None:
            logger.debug("Setting not found: %s", key)
            return None

        if setting.is_encrypted:
            try:
                return self.encryption.decrypt(setting.value)
            except ValueError:
                logger.warning("Failed to decrypt setting: %s", key)
                return None

        return setting.value

    def set(self, key: str, value: str, user_id: str, category: str = "general") -> Setting:
        """
        Set a setting value for a user, creating or updating as needed.

        Automatically encrypts sensitive values.

        Args:
            key: The setting key (e.g., "llm.default_provider").
            value: The value to store.
            user_id: The user ID who owns the setting.
            category: Category for grouping ("llm", "embedding", "agent").

        Returns:
            The created or updated Setting instance.
        """
        logger.debug("Setting value for key: %s (user_id=%s, category: %s)", key, user_id, category)

        is_sensitive = key in self.SENSITIVE_KEYS
        stored_value = value

        if is_sensitive and value:
            stored_value = self.encryption.encrypt(value)
            logger.debug("Encrypted value for key: %s", key)

        # Check if setting exists for this user
        stmt = select(Setting).where(Setting.key == key, Setting.user_id == user_id)
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing:
            existing.value = stored_value
            existing.is_encrypted = is_sensitive
            existing.category = category
            self.db.commit()
            self.db.refresh(existing)
            logger.debug("Updated setting: %s", key)
            return existing

        # Create new setting
        setting = Setting(
            key=key,
            value=stored_value,
            user_id=user_id,
            is_encrypted=is_sensitive,
            category=category,
        )
        self.db.add(setting)
        self.db.commit()
        self.db.refresh(setting)
        logger.debug("Created setting: %s", key)
        return setting

    def get_all(self, user_id: str, category: str | None = None) -> dict[str, str]:
        """
        Get all settings for a user as a dictionary.

        Automatically decrypts sensitive values.

        Args:
            user_id: The user ID who owns the settings.
            category: Optional category filter.

        Returns:
            Dictionary of key-value pairs (decrypted).
        """
        logger.debug("Fetching all settings (user_id=%s, category: %s)", user_id, category)
        stmt = select(Setting).where(Setting.user_id == user_id)
        if category:
            stmt = stmt.where(Setting.category == category)

        settings = self.db.execute(stmt).scalars().all()
        result: dict[str, str] = {}

        for setting in settings:
            if setting.is_encrypted:
                try:
                    result[setting.key] = self.encryption.decrypt(setting.value)
                except ValueError:
                    logger.warning("Failed to decrypt setting: %s", setting.key)
                    result[setting.key] = ""
            else:
                result[setting.key] = setting.value

        logger.debug("Retrieved %d settings", len(result))
        return result

    def get_all_masked(self, user_id: str, category: str | None = None) -> dict[str, str]:
        """
        Get all settings for a user with sensitive values masked.

        Use this for API responses to avoid exposing API keys.

        Args:
            user_id: The user ID who owns the settings.
            category: Optional category filter.

        Returns:
            Dictionary of key-value pairs (sensitive values masked).
        """
        logger.debug("Fetching all settings masked (user_id=%s, category: %s)", user_id, category)
        stmt = select(Setting).where(Setting.user_id == user_id)
        if category:
            stmt = stmt.where(Setting.category == category)

        settings = self.db.execute(stmt).scalars().all()
        result: dict[str, str] = {}

        for setting in settings:
            if setting.is_encrypted:
                result[setting.key] = self.MASKED_VALUE
            else:
                result[setting.key] = setting.value

        logger.debug("Retrieved %d settings (masked)", len(result))
        return result

    def is_key_configured(self, key: str, user_id: str) -> bool:
        """
        Check if a sensitive key has a value configured for a user.

        Args:
            key: The setting key to check.
            user_id: The user ID who owns the setting.

        Returns:
            True if the key exists and has a non-empty value.
        """
        stmt = select(Setting).where(Setting.key == key, Setting.user_id == user_id)
        setting = self.db.execute(stmt).scalar_one_or_none()
        return setting is not None and bool(setting.value)

    def delete(self, key: str, user_id: str) -> bool:
        """
        Delete a setting by key for a user.

        Args:
            key: The setting key to delete.
            user_id: The user ID who owns the setting.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting setting: %s (user_id=%s)", key, user_id)
        stmt = select(Setting).where(Setting.key == key, Setting.user_id == user_id)
        setting = self.db.execute(stmt).scalar_one_or_none()

        if setting is None:
            logger.debug("Setting not found for deletion: %s", key)
            return False

        self.db.delete(setting)
        self.db.commit()
        logger.debug("Deleted setting: %s", key)
        return True

    def delete_all(self, user_id: str) -> int:
        """
        Delete all settings for a user.

        Args:
            user_id: The user ID who owns the settings.

        Returns:
            Number of settings deleted.
        """
        logger.debug("Deleting all settings (user_id=%s)", user_id)
        stmt = select(Setting).where(Setting.user_id == user_id)
        settings = list(self.db.execute(stmt).scalars().all())
        count = len(settings)

        for setting in settings:
            self.db.delete(setting)

        self.db.commit()
        logger.debug("Deleted %d settings", count)
        return count
