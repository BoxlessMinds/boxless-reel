"""Invitation management service."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.config import settings
from src.models.invitation import Invitation
from src.repositories.invitation_repository import InvitationRepository
from src.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class InvitationLimitError(Exception):
    """Exception raised when invitation limit is reached."""

    pass


class InvitationExistsError(Exception):
    """Exception raised when invitation already exists."""

    pass


class InvitationNotFoundError(Exception):
    """Exception raised when invitation is not found."""

    pass


class InvitationService:
    """Service for invitation management operations."""

    def __init__(
        self,
        invitation_repository: InvitationRepository,
        user_repository: UserRepository,
    ) -> None:
        """Initialize invitation service with repositories.

        Args:
            invitation_repository: Repository for invitation operations.
            user_repository: Repository for user operations.
        """
        self.invitation_repository = invitation_repository
        self.user_repository = user_repository

    def create_invitation(
        self,
        inviter_id: str,
        email: str,
        is_admin: bool = False,
    ) -> Invitation:
        """Create a new invitation.

        Args:
            inviter_id: UUID of the user sending the invitation.
            email: Email address to invite.
            is_admin: Whether the inviter is an admin (bypasses limits).

        Returns:
            Created invitation.

        Raises:
            InvitationLimitError: If non-admin user has reached invitation limit.
            InvitationExistsError: If email already has a pending invitation or is registered.
            ValueError: If user tries to invite themselves.
        """
        logger.debug("Creating invitation for email: %s (inviter=%s)", email, inviter_id)

        email_lower = email.lower()

        # Check if user is trying to invite themselves
        inviter = self.user_repository.get_by_id(inviter_id)
        if inviter and inviter.email.lower() == email_lower:
            raise ValueError("Cannot invite yourself")

        # Check if email is already registered
        if self.user_repository.get_by_email(email_lower):
            raise InvitationExistsError(f"User with email {email} is already registered")

        # Check for existing pending invitation
        existing = self.invitation_repository.get_by_email(email_lower, status="pending")
        if existing:
            raise InvitationExistsError(f"Pending invitation already exists for {email}")

        # Check invitation limit for non-admins
        if not is_admin:
            pending_count = self.invitation_repository.count_pending_by_inviter(inviter_id)
            if pending_count >= settings.max_pending_invitations_per_user:
                raise InvitationLimitError(
                    f"Maximum pending invitations ({settings.max_pending_invitations_per_user}) reached"
                )

        # Create invitation
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.invitation_expire_days)
        invitation = Invitation(
            email=email_lower,
            invited_by_id=inviter_id,
            expires_at=expires_at,
        )

        created = self.invitation_repository.create(invitation)
        logger.info("Invitation created for email: %s (id=%s)", email, created.id)
        return created

    def validate_token(self, token: str) -> dict:
        """Validate an invitation token.

        Args:
            token: Invitation token to validate.

        Returns:
            Dict with invitation details if valid.

        Raises:
            InvitationNotFoundError: If token is not found or invalid.
        """
        logger.debug("Validating invitation token")

        invitation = self.invitation_repository.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError("Invalid invitation token")

        # Update expired status if needed
        if invitation.status == "pending" and invitation.is_expired:
            self.invitation_repository.mark_expired(invitation.id)
            raise InvitationNotFoundError("Invitation has expired")

        if not invitation.is_valid:
            raise InvitationNotFoundError("Invitation is no longer valid")

        # Get inviter info
        inviter = self.user_repository.get_by_id(invitation.invited_by_id)
        inviter_name = inviter.display_name if inviter else "Unknown"

        return {
            "valid": True,
            "email": invitation.email,
            "invited_by": inviter_name,
            "expires_at": invitation.expires_at.isoformat(),
        }

    def revoke_invitation(
        self,
        invitation_id: str,
        user_id: str,
        is_admin: bool = False,
    ) -> Invitation:
        """Revoke a pending invitation.

        Args:
            invitation_id: UUID of the invitation to revoke.
            user_id: UUID of the user revoking the invitation.
            is_admin: Whether the user is an admin.

        Returns:
            Revoked invitation.

        Raises:
            InvitationNotFoundError: If invitation not found.
            PermissionError: If user doesn't have permission to revoke.
        """
        logger.debug("Revoking invitation: %s (user=%s)", invitation_id, user_id)

        invitation = self.invitation_repository.get_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError("Invitation not found")

        # Check permission (owner or admin)
        if not is_admin and invitation.invited_by_id != user_id:
            raise PermissionError("Not authorized to revoke this invitation")

        if invitation.status != "pending":
            raise InvitationNotFoundError("Can only revoke pending invitations")

        revoked = self.invitation_repository.mark_revoked(invitation_id)
        logger.info("Invitation revoked: %s", invitation_id)
        return revoked

    def list_invitations(
        self,
        user_id: str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Invitation], int]:
        """List invitations sent by a user.

        Args:
            user_id: UUID of the user.
            status: Optional status filter.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Tuple of (list of invitations, total count).
        """
        logger.debug("Listing invitations for user: %s", user_id)

        # Clean up expired invitations first
        self.invitation_repository.expire_old_invitations()

        invitations = self.invitation_repository.list_by_inviter(
            inviter_id=user_id,
            status=status,
            skip=skip,
            limit=limit,
        )
        total = self.invitation_repository.count_by_inviter(user_id, status=status)
        return invitations, total

    def list_all_invitations(
        self,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Invitation], int]:
        """List all invitations (admin function).

        Args:
            status: Optional status filter.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Tuple of (list of invitations, total count).
        """
        logger.debug("Listing all invitations")

        # Clean up expired invitations first
        self.invitation_repository.expire_old_invitations()

        invitations = self.invitation_repository.list_all(
            status=status,
            skip=skip,
            limit=limit,
        )
        total = self.invitation_repository.count_all(status=status)
        return invitations, total

    def create_bulk_invitations(
        self,
        inviter_id: str,
        emails: list[str],
    ) -> tuple[list[Invitation], list[dict]]:
        """Create multiple invitations at once (admin function).

        Args:
            inviter_id: UUID of the admin user.
            emails: List of email addresses to invite.

        Returns:
            Tuple of (list of created invitations, list of errors).
        """
        logger.debug("Creating bulk invitations for %d emails", len(emails))

        created = []
        errors = []

        for email in emails:
            try:
                invitation = self.create_invitation(
                    inviter_id=inviter_id,
                    email=email,
                    is_admin=True,  # Bypass limits for bulk
                )
                created.append(invitation)
            except (InvitationExistsError, ValueError) as e:
                errors.append({"email": email, "error": str(e)})

        logger.info("Bulk invitations: %d created, %d errors", len(created), len(errors))
        return created, errors

    def get_invitation_link(self, invitation: Invitation) -> str:
        """Generate the registration link for an invitation.

        Args:
            invitation: Invitation object.

        Returns:
            Full registration URL with token.
        """
        return f"{settings.frontend_url}/register?token={invitation.token}"

    def delete_invitation(
        self,
        invitation_id: str,
        user_id: str,
        is_admin: bool = False,
    ) -> bool:
        """Delete an invitation permanently.

        Args:
            invitation_id: UUID of the invitation to delete.
            user_id: UUID of the user deleting the invitation.
            is_admin: Whether the user is an admin.

        Returns:
            True if deleted successfully.

        Raises:
            InvitationNotFoundError: If invitation not found.
            PermissionError: If user doesn't have permission to delete.
        """
        logger.debug("Deleting invitation: %s (user=%s)", invitation_id, user_id)

        invitation = self.invitation_repository.get_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError("Invitation not found")

        # Check permission (owner or admin)
        if not is_admin and invitation.invited_by_id != user_id:
            raise PermissionError("Not authorized to delete this invitation")

        deleted = self.invitation_repository.delete(invitation_id)
        if deleted:
            logger.info("Invitation deleted: %s", invitation_id)
        return deleted


def get_invitation_service(db: Session) -> InvitationService:
    """Factory function for InvitationService dependency injection.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Configured InvitationService instance.
    """
    invitation_repository = InvitationRepository(db)
    user_repository = UserRepository(db)
    return InvitationService(invitation_repository, user_repository)
