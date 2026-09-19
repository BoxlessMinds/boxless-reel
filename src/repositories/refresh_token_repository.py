"""Repository for refresh token database operations."""

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.refresh_token import RefreshToken

logger = logging.getLogger(__name__)


class RefreshTokenRepository:
    """Data access layer for refresh token operations."""

    def __init__(self, db: Session) -> None:
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for secure storage.

        Args:
            token: Raw refresh token.

        Returns:
            SHA-256 hash of the token.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def create(
        self,
        user_id: str,
        token: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Create a new refresh token record.

        Args:
            user_id: UUID of the user.
            token: Raw refresh token (will be hashed).
            expires_at: Token expiration datetime.

        Returns:
            The persisted refresh token record.
        """
        logger.debug("Creating refresh token for user: %s", user_id)
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=self.hash_token(token),
            expires_at=expires_at,
        )
        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)
        logger.debug("Created refresh token with id: %s", refresh_token.id)
        return refresh_token

    def get_by_token(self, token: str) -> RefreshToken | None:
        """Get a refresh token by its raw token value.

        Args:
            token: Raw refresh token.

        Returns:
            RefreshToken if found, None otherwise.
        """
        logger.debug("Fetching refresh token")
        token_hash = self.hash_token(token)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Refresh token not found")
        return result

    def get_valid_token(self, token: str) -> RefreshToken | None:
        """Get a valid (not revoked, not expired) refresh token.

        Args:
            token: Raw refresh token.

        Returns:
            RefreshToken if found and valid, None otherwise.
        """
        logger.debug("Fetching valid refresh token")
        refresh_token = self.get_by_token(token)
        if refresh_token is None:
            return None
        if not refresh_token.is_valid:
            logger.debug("Refresh token is invalid (revoked or expired)")
            return None
        return refresh_token

    def revoke(self, token: str) -> bool:
        """Revoke a refresh token.

        Args:
            token: Raw refresh token.

        Returns:
            True if revoked, False if not found.
        """
        logger.debug("Revoking refresh token")
        refresh_token = self.get_by_token(token)
        if refresh_token is None:
            logger.debug("Refresh token not found for revocation")
            return False
        refresh_token.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.debug("Revoked refresh token: %s", refresh_token.id)
        return True

    def revoke_all_for_user(self, user_id: UUID | str) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: UUID of the user.

        Returns:
            Number of tokens revoked.
        """
        logger.debug("Revoking all refresh tokens for user: %s", user_id)
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == str(user_id),
            RefreshToken.revoked_at.is_(None),
        )
        tokens = list(self.db.execute(stmt).scalars().all())
        count = len(tokens)

        now = datetime.now(timezone.utc)
        for token in tokens:
            token.revoked_at = now

        if count > 0:
            self.db.commit()
        logger.debug("Revoked %d refresh tokens for user: %s", count, user_id)
        return count

    def cleanup_expired(self) -> int:
        """Delete expired refresh tokens from the database.

        Returns:
            Number of tokens deleted.
        """
        logger.debug("Cleaning up expired refresh tokens")
        stmt = select(RefreshToken).where(
            RefreshToken.expires_at < datetime.now(timezone.utc)
        )
        expired_tokens = list(self.db.execute(stmt).scalars().all())
        count = len(expired_tokens)

        for token in expired_tokens:
            self.db.delete(token)

        if count > 0:
            self.db.commit()
        logger.debug("Deleted %d expired refresh tokens", count)
        return count

    def delete(self, token_id: UUID | str) -> bool:
        """Delete a refresh token by ID.

        Args:
            token_id: UUID of the refresh token.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting refresh token: %s", token_id)
        stmt = select(RefreshToken).where(RefreshToken.id == str(token_id))
        token = self.db.execute(stmt).scalar_one_or_none()
        if token is None:
            logger.debug("Refresh token not found for deletion: %s", token_id)
            return False
        self.db.delete(token)
        self.db.commit()
        logger.debug("Deleted refresh token: %s", token_id)
        return True
