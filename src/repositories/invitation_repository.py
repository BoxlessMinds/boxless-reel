"""Repository for invitation database operations."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.invitation import Invitation

logger = logging.getLogger(__name__)


class InvitationRepository:
    """Data access layer for invitation operations."""

    def __init__(self, db: Session) -> None:
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(self, invitation: Invitation) -> Invitation:
        """Create a new invitation record.

        Args:
            invitation: Invitation model instance to persist.

        Returns:
            The persisted invitation with generated ID and token.
        """
        logger.debug("Creating invitation for email: %s", invitation.email)
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        logger.debug("Created invitation with id: %s", invitation.id)
        return invitation

    def get_by_id(self, invitation_id: UUID | str) -> Invitation | None:
        """Get an invitation by its ID.

        Args:
            invitation_id: UUID of the invitation.

        Returns:
            Invitation if found, None otherwise.
        """
        logger.debug("Fetching invitation by id: %s", invitation_id)
        stmt = select(Invitation).where(Invitation.id == str(invitation_id))
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Invitation not found: %s", invitation_id)
        return result

    def get_by_token(self, token: str) -> Invitation | None:
        """Get an invitation by its token.

        Args:
            token: Unique invitation token.

        Returns:
            Invitation if found, None otherwise.
        """
        logger.debug("Fetching invitation by token")
        stmt = select(Invitation).where(Invitation.token == token)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Invitation not found for token")
        return result

    def get_by_email(self, email: str, status: str | None = None) -> Invitation | None:
        """Get an invitation by email address.

        Args:
            email: Invitee's email address.
            status: Optional status filter (e.g., "pending").

        Returns:
            Invitation if found, None otherwise.
        """
        logger.debug("Fetching invitation by email: %s (status=%s)", email, status)
        stmt = select(Invitation).where(Invitation.email == email.lower())
        if status:
            stmt = stmt.where(Invitation.status == status)
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def list_by_inviter(
        self,
        inviter_id: UUID | str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Invitation]:
        """List invitations sent by a specific user.

        Args:
            inviter_id: UUID of the user who sent the invitations.
            status: Optional status filter.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of invitations.
        """
        logger.debug(
            "Listing invitations for inviter: %s (status=%s, skip=%d, limit=%d)",
            inviter_id, status, skip, limit
        )
        stmt = select(Invitation).where(Invitation.invited_by_id == str(inviter_id))
        if status:
            stmt = stmt.where(Invitation.status == status)
        stmt = stmt.order_by(Invitation.created_at.desc()).offset(skip).limit(limit)
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d invitations", len(results))
        return results

    def list_all(
        self,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Invitation]:
        """List all invitations (admin function).

        Args:
            status: Optional status filter.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of all invitations.
        """
        logger.debug("Listing all invitations (status=%s, skip=%d, limit=%d)", status, skip, limit)
        stmt = select(Invitation)
        if status:
            stmt = stmt.where(Invitation.status == status)
        stmt = stmt.order_by(Invitation.created_at.desc()).offset(skip).limit(limit)
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d invitations", len(results))
        return results

    def count_pending_by_inviter(self, inviter_id: UUID | str) -> int:
        """Count pending invitations for a user.

        Args:
            inviter_id: UUID of the user who sent the invitations.

        Returns:
            Count of pending invitations.
        """
        logger.debug("Counting pending invitations for inviter: %s", inviter_id)
        stmt = (
            select(func.count())
            .select_from(Invitation)
            .where(Invitation.invited_by_id == str(inviter_id))
            .where(Invitation.status == "pending")
        )
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Pending invitation count: %d", count)
        return count

    def count_by_inviter(self, inviter_id: UUID | str, status: str | None = None) -> int:
        """Count invitations for a user, optionally filtered by status.

        Args:
            inviter_id: UUID of the user who sent the invitations.
            status: Optional status filter.

        Returns:
            Count of matching invitations.
        """
        logger.debug("Counting invitations for inviter: %s (status=%s)", inviter_id, status)
        stmt = (
            select(func.count())
            .select_from(Invitation)
            .where(Invitation.invited_by_id == str(inviter_id))
        )
        if status:
            stmt = stmt.where(Invitation.status == status)
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Invitation count: %d", count)
        return count

    def count_all(self, status: str | None = None) -> int:
        """Count all invitations.

        Args:
            status: Optional status filter.

        Returns:
            Count of invitations.
        """
        logger.debug("Counting all invitations (status=%s)", status)
        stmt = select(func.count()).select_from(Invitation)
        if status:
            stmt = stmt.where(Invitation.status == status)
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Invitation count: %d", count)
        return count

    def mark_accepted(
        self,
        invitation_id: UUID | str,
        registered_user_id: str,
    ) -> Invitation | None:
        """Mark an invitation as accepted.

        Args:
            invitation_id: UUID of the invitation.
            registered_user_id: UUID of the user who registered.

        Returns:
            Updated invitation if found, None otherwise.
        """
        logger.debug("Marking invitation as accepted: %s", invitation_id)
        invitation = self.get_by_id(invitation_id)
        if invitation is None:
            return None
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        invitation.registered_user_id = registered_user_id
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def mark_revoked(self, invitation_id: UUID | str) -> Invitation | None:
        """Mark an invitation as revoked.

        Args:
            invitation_id: UUID of the invitation.

        Returns:
            Updated invitation if found, None otherwise.
        """
        logger.debug("Marking invitation as revoked: %s", invitation_id)
        invitation = self.get_by_id(invitation_id)
        if invitation is None:
            return None
        invitation.status = "revoked"
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def mark_expired(self, invitation_id: UUID | str) -> Invitation | None:
        """Mark an invitation as expired.

        Args:
            invitation_id: UUID of the invitation.

        Returns:
            Updated invitation if found, None otherwise.
        """
        logger.debug("Marking invitation as expired: %s", invitation_id)
        invitation = self.get_by_id(invitation_id)
        if invitation is None:
            return None
        invitation.status = "expired"
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def expire_old_invitations(self) -> int:
        """Mark all expired invitations as expired.

        Returns:
            Number of invitations marked as expired.
        """
        logger.debug("Expiring old invitations")
        stmt = select(Invitation).where(
            Invitation.status == "pending",
            Invitation.expires_at < datetime.now(timezone.utc),
        )
        expired_invitations = list(self.db.execute(stmt).scalars().all())
        count = len(expired_invitations)

        for invitation in expired_invitations:
            invitation.status = "expired"

        if count > 0:
            self.db.commit()
        logger.debug("Expired %d invitations", count)
        return count

    def delete(self, invitation_id: UUID | str) -> bool:
        """Delete an invitation by ID.

        Args:
            invitation_id: UUID of the invitation to delete.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting invitation: %s", invitation_id)
        invitation = self.get_by_id(invitation_id)
        if invitation is None:
            logger.debug("Invitation not found for deletion: %s", invitation_id)
            return False
        self.db.delete(invitation)
        self.db.commit()
        logger.debug("Deleted invitation: %s", invitation_id)
        return True
