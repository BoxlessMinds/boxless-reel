"""API routes for admin operations."""

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentAdmin
from src.schemas import (
    AdminUserUpdateRequest,
    BulkInvitationRequest,
    BulkInvitationResponse,
    InvitationListResponse,
    InvitationResponse,
    RegistrationModeResponse,
    RegistrationModeUpdateRequest,
    UserListResponse,
    UserResponse,
)
from src.services import (
    InvitationExistsError,
    InvitationService,
    SystemSettingsService,
    UserService,
    get_invitation_service,
    get_system_settings_service,
    get_user_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_user_service(db: Session = Depends(get_db)) -> UserService:
    """Dependency injection for UserService."""
    return get_user_service(db)


def _get_invitation_service(db: Session = Depends(get_db)) -> InvitationService:
    """Dependency injection for InvitationService."""
    return get_invitation_service(db)


def _get_system_settings_service(db: Session = Depends(get_db)) -> SystemSettingsService:
    """Dependency injection for SystemSettingsService."""
    return get_system_settings_service(db)


@router.get("/settings/registration-mode", response_model=RegistrationModeResponse)
async def get_registration_mode(
    current_admin: CurrentAdmin,
    system_settings: SystemSettingsService = Depends(_get_system_settings_service),
) -> RegistrationModeResponse:
    """
    Get current registration mode (admin only).

    Args:
        current_admin: Authenticated admin user.
        system_settings: Injected SystemSettingsService.

    Returns:
        Current registration mode.
    """
    return RegistrationModeResponse(
        require_invitation=system_settings.is_invitation_required()
    )


@router.put("/settings/registration-mode", response_model=RegistrationModeResponse)
async def update_registration_mode(
    request: RegistrationModeUpdateRequest,
    current_admin: CurrentAdmin,
    system_settings: SystemSettingsService = Depends(_get_system_settings_service),
) -> RegistrationModeResponse:
    """
    Toggle registration mode (admin only).

    Args:
        request: New registration mode.
        current_admin: Authenticated admin user.
        system_settings: Injected SystemSettingsService.

    Returns:
        Updated registration mode.
    """
    system_settings.update_setting(
        key="registration.require_invitation",
        value=str(request.require_invitation).lower(),
        admin_user_id=current_admin.id,
    )

    logger.info(
        "Admin %s set registration mode: require_invitation=%s",
        current_admin.email,
        request.require_invitation,
    )

    return RegistrationModeResponse(require_invitation=request.require_invitation)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_admin: CurrentAdmin,
    search: str | None = Query(None, description="Search in email and display name"),
    role: str | None = Query(None, pattern="^(admin|user)$", description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user_service: UserService = Depends(_get_user_service),
) -> UserListResponse:
    """
    List all users (admin only).

    Args:
        current_admin: Authenticated admin user.
        search: Search term for email/display name.
        role: Filter by role.
        is_active: Filter by active status.
        page: Page number (1-indexed).
        page_size: Items per page.
        user_service: Injected UserService.

    Returns:
        Paginated list of users.
    """
    skip = (page - 1) * page_size

    users, total = user_service.list_users(
        skip=skip,
        limit=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    user_list = [UserResponse.model_validate(u) for u in users]

    logger.debug("Admin %s listed %d users", current_admin.email, len(user_list))
    return UserListResponse(
        users=user_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: AdminUserUpdateRequest,
    current_admin: CurrentAdmin,
    user_service: UserService = Depends(_get_user_service),
) -> UserResponse:
    """
    Update a user's status or role (admin only).

    Args:
        user_id: UUID of the user to update.
        request: Fields to update.
        current_admin: Authenticated admin user.
        user_service: Injected UserService.

    Returns:
        Updated user profile.

    Raises:
        HTTPException: 404 if user not found.
    """
    updated_user = user_service.update_user(
        user_id=user_id,
        is_active=request.is_active,
        role=request.role,
    )

    if updated_user is None:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    logger.info("Admin %s updated user %s", current_admin.email, user_id)
    return UserResponse.model_validate(updated_user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: CurrentAdmin,
    user_service: UserService = Depends(_get_user_service),
) -> dict:
    """
    Delete a user (admin only).

    Args:
        user_id: UUID of the user to delete.
        current_admin: Authenticated admin user.
        user_service: Injected UserService.

    Returns:
        Success message.

    Raises:
        HTTPException: 400 if trying to delete yourself.
        HTTPException: 404 if user not found.
    """
    try:
        deleted = user_service.delete_user(
            user_id=user_id,
            admin_user_id=current_admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not deleted:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    logger.info("Admin %s deleted user %s", current_admin.email, user_id)
    return {"message": "User deleted successfully"}


@router.get("/invitations", response_model=InvitationListResponse)
async def list_all_invitations(
    current_admin: CurrentAdmin,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> InvitationListResponse:
    """
    List all invitations (admin only).

    Args:
        current_admin: Authenticated admin user.
        invitation_service: Injected InvitationService.

    Returns:
        List of all invitations.
    """
    invitations_list, total = invitation_service.list_all_invitations()

    invitation_items = [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            token=None,  # Don't expose tokens in admin view
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in invitations_list
    ]

    logger.debug("Admin %s listed %d invitations", current_admin.email, len(invitation_items))
    return InvitationListResponse(invitations=invitation_items, total=total)


@router.post("/invitations/bulk", response_model=BulkInvitationResponse)
async def bulk_create_invitations(
    request: BulkInvitationRequest,
    current_admin: CurrentAdmin,
    invitation_service: InvitationService = Depends(_get_invitation_service),
) -> BulkInvitationResponse:
    """
    Create multiple invitations at once (admin only).

    Args:
        request: List of emails to invite.
        current_admin: Authenticated admin user.
        invitation_service: Injected InvitationService.

    Returns:
        Results with created and failed invitations.
    """
    created = []
    failed = []

    for email in request.emails:
        try:
            invitation_service.create_invitation(
                inviter_id=current_admin.id,
                email=email,
                is_admin=True,
            )
            created.append(email)
        except InvitationExistsError as e:
            failed.append({"email": email, "reason": str(e)})
        except Exception as e:
            logger.error("Failed to create invitation for %s: %s", email, e)
            failed.append({"email": email, "reason": "Internal error"})

    logger.info(
        "Admin %s bulk created invitations: %d created, %d failed",
        current_admin.email,
        len(created),
        len(failed),
    )

    return BulkInvitationResponse(created=created, failed=failed)
