"""Service for system-wide settings with priority chain: DB -> env var -> default."""

import logging
import os

from sqlalchemy.orm import Session

from src.repositories.system_settings_repository import SystemSettingsRepository

logger = logging.getLogger(__name__)

# Default values for system settings
DEFAULTS: dict[str, str] = {
    "registration.require_invitation": "true",
}

# Mapping from setting keys to environment variable names
ENV_VAR_MAP: dict[str, str] = {
    "registration.require_invitation": "REQUIRE_INVITATION_CODE",
}


class SystemSettingsService:
    """Service for managing system-wide settings.

    Settings are resolved with a priority chain:
    1. Database value (set by admin via UI)
    2. Environment variable
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

        Priority: Database -> Environment Variable -> Default

        Args:
            key: Setting key.

        Returns:
            The resolved setting value, or None if not found anywhere.
        """
        # 1. Check database (admin override)
        db_value = self.repository.get(key)
        if db_value is not None:
            return db_value

        # 2. Check environment variable
        env_var = ENV_VAR_MAP.get(key)
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value is not None:
                return env_value.lower()

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
