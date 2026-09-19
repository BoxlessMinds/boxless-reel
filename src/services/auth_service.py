"""Authentication service for JWT token management and user authentication."""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.config import settings
from src.models.user import User
from src.repositories.refresh_token_repository import RefreshTokenRepository
from src.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthenticationError(Exception):
    """Exception raised when authentication fails."""

    pass


class TokenError(Exception):
    """Exception raised when token operations fail."""

    pass


class AuthService:
    """Service for authentication and token management."""

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        """Initialize auth service with repositories.

        Args:
            user_repository: Repository for user operations.
            refresh_token_repository: Repository for refresh token operations.
        """
        self.user_repository = user_repository
        self.refresh_token_repository = refresh_token_repository

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password.

        Returns:
            Hashed password.
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash.

        Args:
            plain_password: Plain text password.
            hashed_password: Hashed password.

        Returns:
            True if password matches, False otherwise.
        """
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: str) -> str:
        """Create a JWT access token.

        Args:
            user_id: UUID of the user.

        Returns:
            Encoded JWT access token.
        """
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expire,
            "type": "access",
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        logger.debug("Created access token for user: %s", user_id)
        return token

    def create_refresh_token(self, user_id: str) -> str:
        """Create a refresh token and store it in the database.

        Args:
            user_id: UUID of the user.

        Returns:
            Raw refresh token string.
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

        self.refresh_token_repository.create(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )
        logger.debug("Created refresh token for user: %s", user_id)
        return token

    def authenticate(self, email: str, password: str) -> tuple[User, str, str]:
        """Authenticate a user and return tokens.

        Args:
            email: User's email address.
            password: User's password.

        Returns:
            Tuple of (User, access_token, refresh_token).

        Raises:
            AuthenticationError: If authentication fails.
        """
        logger.debug("Authenticating user: %s", email)

        user = self.user_repository.get_by_email(email.lower())
        if user is None:
            logger.debug("User not found: %s", email)
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            logger.debug("User account is deactivated: %s", email)
            raise AuthenticationError("Account is deactivated")

        if not self.verify_password(password, user.password_hash):
            logger.debug("Invalid password for user: %s", email)
            raise AuthenticationError("Invalid email or password")

        # Update last login
        self.user_repository.update_last_login(user.id)

        # Generate tokens
        access_token = self.create_access_token(user.id)
        refresh_token = self.create_refresh_token(user.id)

        logger.info("User authenticated successfully: %s", email)
        return user, access_token, refresh_token

    def refresh_tokens(self, refresh_token: str) -> tuple[str, str]:
        """Refresh access and refresh tokens.

        Args:
            refresh_token: Current refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token).

        Raises:
            TokenError: If refresh token is invalid.
        """
        logger.debug("Refreshing tokens")

        token_record = self.refresh_token_repository.get_valid_token(refresh_token)
        if token_record is None:
            logger.debug("Invalid or expired refresh token")
            raise TokenError("Invalid or expired refresh token")

        # Verify user still exists and is active
        user = self.user_repository.get_by_id(token_record.user_id)
        if user is None or not user.is_active:
            logger.debug("User not found or inactive for refresh token")
            raise TokenError("User not found or inactive")

        # Revoke old token
        self.refresh_token_repository.revoke(refresh_token)

        # Generate new tokens
        new_access_token = self.create_access_token(user.id)
        new_refresh_token = self.create_refresh_token(user.id)

        logger.debug("Tokens refreshed for user: %s", user.id)
        return new_access_token, new_refresh_token

    def logout(self, refresh_token: str) -> bool:
        """Logout by revoking the refresh token.

        Args:
            refresh_token: Refresh token to revoke.

        Returns:
            True if token was revoked, False if not found.
        """
        logger.debug("Logging out user")
        result = self.refresh_token_repository.revoke(refresh_token)
        if result:
            logger.debug("Refresh token revoked successfully")
        return result

    def logout_all_sessions(self, user_id: str) -> int:
        """Logout from all sessions by revoking all refresh tokens.

        Args:
            user_id: UUID of the user.

        Returns:
            Number of tokens revoked.
        """
        logger.debug("Logging out all sessions for user: %s", user_id)
        count = self.refresh_token_repository.revoke_all_for_user(user_id)
        logger.debug("Revoked %d refresh tokens for user: %s", count, user_id)
        return count

    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID.

        Args:
            user_id: UUID of the user.

        Returns:
            User if found, None otherwise.
        """
        return self.user_repository.get_by_id(user_id)

    def update_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        current_password: str | None = None,
        new_password: str | None = None,
    ) -> User:
        """Update user profile.

        Args:
            user_id: UUID of the user.
            display_name: New display name (optional).
            current_password: Current password (required if changing password).
            new_password: New password (optional).

        Returns:
            Updated user.

        Raises:
            AuthenticationError: If current password is incorrect.
            ValueError: If user not found.
        """
        logger.debug("Updating profile for user: %s", user_id)

        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if display_name is not None:
            user.display_name = display_name

        if new_password is not None:
            if current_password is None:
                raise AuthenticationError("Current password required to change password")
            if not self.verify_password(current_password, user.password_hash):
                raise AuthenticationError("Current password is incorrect")
            user.password_hash = self.hash_password(new_password)

        return self.user_repository.update(user)


def get_auth_service(db: Session) -> AuthService:
    """Factory function for AuthService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured AuthService instance.
    """
    user_repository = UserRepository(db)
    refresh_token_repository = RefreshTokenRepository(db)
    return AuthService(user_repository, refresh_token_repository)
