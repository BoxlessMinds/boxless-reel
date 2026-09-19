"""Repository for user database operations."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.user import User

logger = logging.getLogger(__name__)


class UserRepository:
    """Data access layer for user operations."""

    def __init__(self, db: Session) -> None:
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(self, user: User) -> User:
        """Create a new user record.

        Args:
            user: User model instance to persist.

        Returns:
            The persisted user with generated ID.
        """
        logger.debug("Creating user with email: %s", user.email)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        logger.debug("Created user with id: %s", user.id)
        return user

    def get_by_id(self, user_id: UUID | str) -> User | None:
        """Get a user by their ID.

        Args:
            user_id: UUID of the user.

        Returns:
            User if found, None otherwise.
        """
        logger.debug("Fetching user by id: %s", user_id)
        stmt = select(User).where(User.id == str(user_id))
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("User not found: %s", user_id)
        return result

    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address.

        Args:
            email: User's email address.

        Returns:
            User if found, None otherwise.
        """
        logger.debug("Fetching user by email: %s", email)
        stmt = select(User).where(User.email == email.lower())
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("User not found with email: %s", email)
        return result

    def update(self, user: User) -> User:
        """Update an existing user record.

        Args:
            user: User model instance with updated fields.

        Returns:
            The updated user.
        """
        logger.debug("Updating user: %s", user.id)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_last_login(self, user_id: UUID | str) -> None:
        """Update the last login timestamp for a user.

        Args:
            user_id: UUID of the user.
        """
        logger.debug("Updating last login for user: %s", user_id)
        user = self.get_by_id(user_id)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            self.db.commit()

    def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> list[User]:
        """List users with filtering and pagination.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            search: Search term for email and display_name (case-insensitive).
            role: Filter by role ("admin" or "user").
            is_active: Filter by active status.

        Returns:
            List of matching users.
        """
        logger.debug(
            "Listing users (skip=%d, limit=%d, search=%s, role=%s, is_active=%s)",
            skip, limit, search, role, is_active
        )
        stmt = select(User)

        if search:
            search_pattern = f"%{search}%"
            from sqlalchemy import or_
            stmt = stmt.where(
                or_(
                    User.email.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        if role:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d users", len(results))
        return results

    def count(
        self,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Count users matching the filters.

        Args:
            search: Search term for email and display_name (case-insensitive).
            role: Filter by role.
            is_active: Filter by active status.

        Returns:
            Count of matching users.
        """
        logger.debug("Counting users (search=%s, role=%s, is_active=%s)", search, role, is_active)
        stmt = select(func.count()).select_from(User)

        if search:
            search_pattern = f"%{search}%"
            from sqlalchemy import or_
            stmt = stmt.where(
                or_(
                    User.email.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        if role:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Count result: %d", count)
        return count

    def delete(self, user_id: UUID | str) -> bool:
        """Delete a user by ID.

        Args:
            user_id: UUID of the user to delete.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting user: %s", user_id)
        user = self.get_by_id(user_id)
        if user is None:
            logger.debug("User not found for deletion: %s", user_id)
            return False
        self.db.delete(user)
        self.db.commit()
        logger.debug("Deleted user: %s", user_id)
        return True
