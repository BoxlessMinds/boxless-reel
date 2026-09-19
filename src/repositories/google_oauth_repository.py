"""Repository for Google OAuth credential database operations."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.google_oauth_credential import GoogleOAuthCredential
from src.utils.encryption import SettingsEncryption, get_encryption

logger = logging.getLogger(__name__)


class GoogleOAuthRepository:
    """Data access layer for Google OAuth credential operations.

    Encrypts access/refresh tokens before writing and never decrypts them
    back onto a tracked model instance. `get_by_user_id` returns the row
    exactly as stored: `access_token`/`refresh_token` remain Fernet
    ciphertext on the returned instance. A caller that needs cleartext must
    decrypt into a local variable via `self.encryption.decrypt(...)` — never
    assign the result back onto the model, or a later `db.commit()` on that
    session would flush the decrypted plaintext back into the column.

    Does queries and at-rest encryption formatting only — no HTTP calls, no
    OAuth logic, no business rules.
    """

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

    def upsert(
        self,
        user_id: str,
        google_account_email: str,
        google_account_id: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime,
        scopes: str,
    ) -> GoogleOAuthCredential:
        """
        Create or update the Google OAuth credential for a user.

        Args:
            user_id: The app user this credential belongs to.
            google_account_email: The connected Google account's email.
            google_account_id: Google's stable account id (the `sub` claim).
            access_token: Plaintext access token; encrypted before storage.
            refresh_token: Plaintext refresh token; encrypted before storage.
            token_expires_at: Expiry timestamp of the access token.
            scopes: Space-separated OAuth scope string.

        Returns:
            The persisted GoogleOAuthCredential (tokens stored as ciphertext).
        """
        logger.debug("Upserting Google OAuth credential (user_id=%s)", user_id)
        stmt = select(GoogleOAuthCredential).where(
            GoogleOAuthCredential.user_id == user_id
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        encrypted_access_token = self.encryption.encrypt(access_token)
        encrypted_refresh_token = self.encryption.encrypt(refresh_token)

        if existing:
            existing.google_account_email = google_account_email
            existing.google_account_id = google_account_id
            existing.access_token = encrypted_access_token
            existing.refresh_token = encrypted_refresh_token
            existing.token_expires_at = token_expires_at
            existing.scopes = scopes
            self.db.commit()
            self.db.refresh(existing)
            logger.debug("Updated Google OAuth credential (user_id=%s)", user_id)
            return existing

        credential = GoogleOAuthCredential(
            user_id=user_id,
            google_account_email=google_account_email,
            google_account_id=google_account_id,
            access_token=encrypted_access_token,
            refresh_token=encrypted_refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
        )
        self.db.add(credential)
        self.db.commit()
        self.db.refresh(credential)
        logger.debug("Created Google OAuth credential (user_id=%s)", user_id)
        return credential

    def get_by_user_id(self, user_id: str) -> GoogleOAuthCredential | None:
        """
        Get the Google OAuth credential for a user.

        The returned instance's `access_token`/`refresh_token` remain Fernet
        ciphertext — this method never decrypts them onto the model.

        Args:
            user_id: The app user to look up.

        Returns:
            The GoogleOAuthCredential, or None if the user has none.
        """
        logger.debug("Fetching Google OAuth credential (user_id=%s)", user_id)
        stmt = select(GoogleOAuthCredential).where(
            GoogleOAuthCredential.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def delete_by_user_id(self, user_id: str) -> bool:
        """
        Delete the Google OAuth credential for a user.

        Removes only the `google_oauth_credentials` row for this user; it
        touches no other table.

        Args:
            user_id: The app user whose credential should be removed.

        Returns:
            True if a row was deleted, False if the user had none.
        """
        logger.debug("Deleting Google OAuth credential (user_id=%s)", user_id)
        stmt = select(GoogleOAuthCredential).where(
            GoogleOAuthCredential.user_id == user_id
        )
        credential = self.db.execute(stmt).scalar_one_or_none()

        if credential is None:
            logger.debug("No Google OAuth credential to delete (user_id=%s)", user_id)
            return False

        self.db.delete(credential)
        self.db.commit()
        logger.debug("Deleted Google OAuth credential (user_id=%s)", user_id)
        return True
