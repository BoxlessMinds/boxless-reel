"""API routes for invitation management."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
    InvitationValidateResponse,
    ValidateTokenRequest,
)
from src.services import (
    InvitationExistsError,
    InvitationLimitError,
    InvitationNotFoundError,
    InvitationService,
    get_invitation_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_invitation_service(db: Session = Depends(get_db)) -> InvitationService:
    """Dependency injection for InvitationService."""
    return get_invitation_service(db)


@router.post("", response_model=InvitationResponse, status_code=201)
async def create_invitation(
    request: InvitationCreateRequest,
    current_user: CurrentUser,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> InvitationResponse:
    """
    Create a new invitation.

    Users can invite others to join. Admins have higher invitation limits.

    Args:
        request: Email to invite.
        current_user: Authenticated user.
        invitation_service: Injected InvitationService.

    Returns:
        Created invitation with invite link.

    Raises:
        HTTPException: 400 if limit reached or email already invited,
                      409 if invitation already exists.
    """
    try:
        invitation = invitation_service.create_invitation(
            inviter_id=current_user.id,
            email=request.email,
            is_admin=current_user.role == "admin",
        )

        # Build response with token
        response_data = {
            "id": invitation.id,
            "email": invitation.email,
            "token": invitation.token,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
            "created_at": invitation.created_at,
        }

        logger.info("Invitation created by %s for %s", current_user.email, request.email)
        return InvitationResponse(**response_data)

    except InvitationLimitError as e:
        logger.warning("Invitation limit reached for %s: %s", current_user.email, e)
        raise HTTPException(status_code=400, detail=str(e))
    except InvitationExistsError as e:
        logger.warning("Invitation already exists: %s", e)
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=InvitationListResponse)
async def list_invitations(
    current_user: CurrentUser,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> InvitationListResponse:
    """
    List invitations sent by the current user.

    Args:
        current_user: Authenticated user.
        invitation_service: Injected InvitationService.

    Returns:
        List of invitations.
    """
    invitations_list, total = invitation_service.list_invitations(current_user.id)

    items = []
    for inv in invitations_list:
        item = InvitationResponse(
            id=inv.id,
            email=inv.email,
            token=inv.token if inv.status == "pending" else None,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        items.append(item)

    logger.debug("Listed %d invitations for user %s", len(items), current_user.email)
    return InvitationListResponse(invitations=items, total=total)


@router.delete("/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    current_user: CurrentUser,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> dict:
    """
    Revoke a pending invitation.

    Users can revoke their own invitations. Admins can revoke any invitation.

    Args:
        invitation_id: UUID of the invitation to revoke.
        current_user: Authenticated user.
        invitation_service: Injected InvitationService.

    Returns:
        Success message.

    Raises:
        HTTPException: 404 if invitation not found or unauthorized.
    """
    try:
        invitation_service.revoke_invitation(
            invitation_id=invitation_id,
            user_id=current_user.id,
            is_admin=current_user.role == "admin",
        )
        logger.info("Invitation %s revoked by %s", invitation_id, current_user.email)
        return {"message": "Invitation revoked successfully"}

    except InvitationNotFoundError as e:
        logger.warning("Revoke failed - invitation not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{invitation_id}/clear")
async def clear_invitation(
    invitation_id: str,
    current_user: CurrentUser,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> dict:
    """
    Permanently delete an invitation from history.

    Use this to remove accepted, expired, or revoked invitations from the list.
    For pending invitations, use the revoke endpoint instead.

    Args:
        invitation_id: UUID of the invitation to delete.
        current_user: Authenticated user.
        invitation_service: Injected InvitationService.

    Returns:
        Success message.

    Raises:
        HTTPException: 404 if invitation not found or unauthorized.
    """
    try:
        invitation_service.delete_invitation(
            invitation_id=invitation_id,
            user_id=current_user.id,
            is_admin=current_user.role == "admin",
        )
        logger.info("Invitation %s cleared by %s", invitation_id, current_user.email)
        return {"message": "Invitation cleared successfully"}

    except InvitationNotFoundError as e:
        logger.warning("Clear failed - invitation not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.warning("Clear failed - permission denied: %s", e)
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/validate", response_model=InvitationValidateResponse)
async def validate_invitation_token(
    request: ValidateTokenRequest,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> InvitationValidateResponse:
    """
    Validate an invitation token (public endpoint).

    Used during registration to verify token validity before completing the form.
    Token is accepted in the request body to avoid exposure in URLs and logs.

    Args:
        request: Request containing the invitation token.
        invitation_service: Injected InvitationService.

    Returns:
        Validation result with email if valid.

    Raises:
        HTTPException: 404 if token is invalid or not found.
    """
    try:
        result = invitation_service.validate_token(request.token)
        return InvitationValidateResponse(
            valid=True,
            email=result.get("email"),
            expires_at=result.get("expires_at"),
        )
    except InvitationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
