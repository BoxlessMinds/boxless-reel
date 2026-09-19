"""User management service."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.config import settings
from src.models.invitation import Invitation
from src.models.user import User
from src.repositories.invitation_repository import InvitationRepository
from src.repositories.user_repository import UserRepository
from src.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class UserExistsError(Exception):
    """Exception raised when trying to create a user that already exists."""

    pass


class InvalidInvitationError(Exception):
    """Exception raised when invitation is invalid."""

    pass


class UserService:
    """Service for user management operations."""

    def __init__(
        self,
        user_repository: UserRepository,
        invitation_repository: InvitationRepository,
    ) -> None:
        """Initialize user service with repositories.

        Args:
            user_repository: Repository for user operations.
            invitation_repository: Repository for invitation operations.
        """
        self.user_repository = user_repository
        self.invitation_repository = invitation_repository

    def create_admin(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        """Create an admin user (for initial bootstrap).

        Args:
            email: Admin's email address.
            password: Admin's password.
            display_name: Admin's display name (defaults to email username).

        Returns:
            Created admin user.

        Raises:
            UserExistsError: If email is already registered.
        """
        logger.info("Creating admin user: %s", email)

        email_lower = email.lower()
        if self.user_repository.get_by_email(email_lower):
            raise UserExistsError(f"User with email {email} already exists")

        if display_name is None:
            display_name = email_lower.split("@")[0]

        user = User(
            email=email_lower,
            password_hash=AuthService.hash_password(password),
            display_name=display_name,
            role="admin",
            is_active=True,
            email_verified=True,  # Admin accounts are auto-verified
        )

        created_user = self.user_repository.create(user)
        logger.info("Admin user created: %s (id=%s)", email, created_user.id)
        return created_user

    def register_from_invitation(
        self,
        token: str,
        email: str,
        password: str,
        display_name: str,
    ) -> User:
        """Register a new user from an invitation.

        Args:
            token: Invitation token.
            email: User's email (must match invitation).
            password: User's chosen password.
            display_name: User's display name.

        Returns:
            Created user.

        Raises:
            InvalidInvitationError: If invitation is invalid, expired, or email doesn't match.
            UserExistsError: If email is already registered.
        """
        logger.debug("Registering user from invitation")

        # Validate invitation
        invitation = self.invitation_repository.get_by_token(token)
        if invitation is None:
            raise InvalidInvitationError("Invalid invitation token")

        if not invitation.is_valid:
            if invitation.is_expired:
                self.invitation_repository.mark_expired(invitation.id)
                raise InvalidInvitationError("Invitation has expired")
            raise InvalidInvitationError("Invitation is no longer valid")

        email_lower = email.lower()
        if invitation.email.lower() != email_lower:
            raise InvalidInvitationError("Email does not match invitation")

        # Check if email already registered
        if self.user_repository.get_by_email(email_lower):
            raise UserExistsError(f"User with email {email} already exists")

        # Create user
        user = User(
            email=email_lower,
            password_hash=AuthService.hash_password(password),
            display_name=display_name,
            role="user",
            is_active=True,
            email_verified=True,  # Verified through invitation
            invited_by_id=invitation.invited_by_id,
        )

        created_user = self.user_repository.create(user)

        # Mark invitation as accepted
        self.invitation_repository.mark_accepted(invitation.id, created_user.id)

        logger.info("User registered from invitation: %s (id=%s)", email, created_user.id)
        return created_user

    def register_open(
        self,
        email: str,
        password: str,
        display_name: str,
    ) -> User:
        """Register a new user via open registration (no invitation required).

        Args:
            email: User's email address.
            password: User's chosen password.
            display_name: User's display name.

        Returns:
            Created user.

        Raises:
            UserExistsError: If email is already registered.
        """
        logger.debug("Registering user via open registration")

        email_lower = email.lower()

        if self.user_repository.get_by_email(email_lower):
            raise UserExistsError(f"User with email {email} already exists")

        user = User(
            email=email_lower,
            password_hash=AuthService.hash_password(password),
            display_name=display_name,
            role="user",
            is_active=True,
            email_verified=False,  # Not verified through invitation
        )

        created_user = self.user_repository.create(user)
        logger.info("User registered via open registration: %s (id=%s)", email, created_user.id)
        return created_user

    def list_users(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """List users with filtering and pagination (admin function).

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            search: Search term for email and display_name.
            role: Filter by role.
            is_active: Filter by active status.

        Returns:
            Tuple of (list of users, total count).
        """
        logger.debug("Listing users (skip=%d, limit=%d)", skip, limit)
        users = self.user_repository.list_all(
            skip=skip,
            limit=limit,
            search=search,
            role=role,
            is_active=is_active,
        )
        total = self.user_repository.count(search=search, role=role, is_active=is_active)
        return users, total

    def update_user(
        self,
        user_id: str,
        is_active: bool | None = None,
        role: str | None = None,
    ) -> User | None:
        """Update a user's status or role (admin function).

        Args:
            user_id: UUID of the user to update.
            is_active: New active status (optional).
            role: New role (optional).

        Returns:
            Updated user, or None if not found.
        """
        logger.debug("Updating user: %s", user_id)

        user = self.user_repository.get_by_id(user_id)
        if user is None:
            return None

        if is_active is not None:
            user.is_active = is_active

        if role is not None:
            if role not in ("admin", "user"):
                raise ValueError("Role must be 'admin' or 'user'")
            user.role = role

        return self.user_repository.update(user)

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
        password: str | None = None,
    ) -> User | None:
        """Update a user's own profile.

        Args:
            user_id: UUID of the user to update.
            display_name: New display name (optional).
            password: New password (optional).

        Returns:
            Updated user, or None if not found.
        """
        logger.debug("Updating user profile: %s", user_id)

        user = self.user_repository.get_by_id(user_id)
        if user is None:
            return None

        if display_name is not None:
            user.display_name = display_name

        if password is not None:
            user.password_hash = AuthService.hash_password(password)

        return self.user_repository.update(user)

    def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email.

        Args:
            email: User's email address.

        Returns:
            User if found, None otherwise.
        """
        return self.user_repository.get_by_email(email.lower())

    def delete_user(self, user_id: str, admin_user_id: str) -> bool:
        """Delete a user (admin function).

        Args:
            user_id: UUID of the user to delete.
            admin_user_id: UUID of the admin performing the deletion.

        Returns:
            True if deleted, False if not found.

        Raises:
            ValueError: If trying to delete yourself.
        """
        logger.debug("Admin %s deleting user: %s", admin_user_id, user_id)

        if user_id == admin_user_id:
            raise ValueError("Cannot delete your own account")

        deleted = self.user_repository.delete(user_id)
        if deleted:
            logger.info("Admin %s deleted user %s", admin_user_id, user_id)
        return deleted


def get_user_service(db: Session) -> UserService:
    """Factory function for UserService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured UserService instance.
    """
    user_repository = UserRepository(db)
    invitation_repository = InvitationRepository(db)
    return UserService(user_repository, invitation_repository)
