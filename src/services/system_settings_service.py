"""Service for system-wide settings with priority chain: DB -> configuration -> default."""

import logging

from sqlalchemy.orm import Session

from src.config import settings
from src.repositories.system_settings_repository import SystemSettingsRepository

logger = logging.getLogger(__name__)

# Fallback values for setting keys that have no Settings field.
# Any key listed in SETTINGS_FIELD_MAP must keep the same default as its
# Settings field in src/config.py, so the two never disagree.
DEFAULTS: dict[str, str] = {
    "registration.require_invitation": "true",
}

# Mapping from setting keys to Settings field names. Reading the loaded
# configuration rather than os.environ means a value written only in .env
# counts, exactly like a real process environment variable.
SETTINGS_FIELD_MAP: dict[str, str] = {
    "registration.require_invitation": "require_invitation_code",
}


class SystemSettingsService:
    """Service for managing system-wide settings.

    Settings are resolved with a priority chain:
    1. Database value (set by admin via UI)
    2. Loaded configuration (a process environment variable or a .env entry)
    3. Hardcoded default
    """

    def __init__(self, repository: SystemSettingsRepository) -> None:
        """Initialize with repository.

        Args:
            repository: SystemSettingsRepository instance.
        """
        self.repository = repository

    def get_effective_value(self, key: str) -> str | None:
        """Get the effective value for a system setting using the priority chain.

        Priority: Database -> Loaded configuration -> Default

        Args:
            key: Setting key.

        Returns:
            The resolved setting value, or None if not found anywhere.
        """
        # 1. Check database (admin override)
        db_value = self.repository.get(key)
        if db_value is not None:
            return db_value

        # 2. Check the loaded configuration (process environment or .env)
        field = SETTINGS_FIELD_MAP.get(key)
        if field is not None:
            configured_value = getattr(settings, field, None)
            if configured_value is not None:
                # The chain is string-typed, so normalise bools and numbers.
                return str(configured_value).lower()

        # 3. Fall back to default
        return DEFAULTS.get(key)

    def is_invitation_required(self) -> bool:
        """Check whether invitation is required for registration.

        Returns:
            True if invitation codes are required, False for open registration.
        """
        value = self.get_effective_value("registration.require_invitation")
        return value != "false"

    def update_setting(self, key: str, value: str, admin_user_id: str) -> None:
        """Update a system setting in the database.

        Args:
            key: Setting key.
            value: New value.
            admin_user_id: UUID of the admin making the change.
        """
        self.repository.set(key, value, updated_by_id=admin_user_id)
        logger.info("Admin %s updated system setting %s = %s", admin_user_id, key, value)


def get_system_settings_service(db: Session) -> SystemSettingsService:
    """Factory function for SystemSettingsService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured SystemSettingsService instance.
    """
    repository = SystemSettingsRepository(db)
    return SystemSettingsService(repository)
