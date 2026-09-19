"""Encryption utilities for securing sensitive settings."""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SettingsEncryption:
    """Handles encryption and decryption of sensitive settings values.

    Uses Fernet symmetric encryption (AES-256-CBC with HMAC).
    The encryption key should be stored in SETTINGS_ENCRYPTION_KEY environment variable.
    """

    _instance: "SettingsEncryption | None" = None
    _key: bytes | None = None

    def __new__(cls) -> "SettingsEncryption":
        """Singleton pattern to ensure consistent encryption key usage."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_key()
        return cls._instance

    def _initialize_key(self) -> None:
        """Initialize the encryption key from environment or generate one."""
        from src.config import settings as app_settings

        key_str = app_settings.settings_encryption_key

        if key_str:
            try:
                # Validate the key format
                self._key = key_str.encode()
                Fernet(self._key)  # This will raise if key is invalid
                logger.debug("Using SETTINGS_ENCRYPTION_KEY from environment")
            except Exception as e:
                logger.error("Invalid SETTINGS_ENCRYPTION_KEY: %s", e)
                raise ValueError(
                    "SETTINGS_ENCRYPTION_KEY must be a valid Fernet key. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                ) from e
        else:
            # Generate a key for development use
            self._key = Fernet.generate_key()
            logger.warning(
                "No SETTINGS_ENCRYPTION_KEY set. Using auto-generated key. "
                "API keys stored in the database will not persist across restarts. "
                "Set SETTINGS_ENCRYPTION_KEY environment variable for production."
            )

    @property
    def fernet(self) -> Fernet:
        """Get the Fernet instance for encryption/decryption."""
        if self._key is None:
            self._initialize_key()
        return Fernet(self._key)

    def encrypt(self, value: str) -> str:
        """Encrypt a string value.

        Args:
            value: The plaintext value to encrypt.

        Returns:
            The encrypted value as a base64-encoded string.
        """
        if not value:
            return ""
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt an encrypted string value.

        Args:
            encrypted_value: The encrypted value (base64-encoded).

        Returns:
            The decrypted plaintext value.

        Raises:
            ValueError: If decryption fails (wrong key or corrupted data).
        """
        if not encrypted_value:
            return ""
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except InvalidToken as e:
            logger.error("Failed to decrypt value - key may have changed")
            raise ValueError(
                "Failed to decrypt value. The encryption key may have changed. "
                "You may need to re-enter your API keys."
            ) from e

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Useful for testing."""
        cls._instance = None
        cls._key = None


def get_encryption() -> SettingsEncryption:
    """Get the settings encryption singleton instance.

    Returns:
        The SettingsEncryption singleton instance.
    """
    return SettingsEncryption()
