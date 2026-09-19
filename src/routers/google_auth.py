"""API routes for Google account connection (YouTube OAuth)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.config import settings
from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    GoogleAuthConnectResponse,
    GoogleAuthDisconnectResponse,
    GoogleOAuthStatusResponse,
)
from src.services import (
    GoogleAuthService,
    GoogleAuthStateError,
    get_google_auth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_google_auth_service(db: Session = Depends(get_db)) -> GoogleAuthService:
    """Dependency that provides GoogleAuthService instance."""
    return get_google_auth_service(db)


@router.get("/connect", response_model=GoogleAuthConnectResponse)
async def connect(
    current_user: CurrentUser,
    service: GoogleAuthService = Depends(_get_google_auth_service),
) -> GoogleAuthConnectResponse:
    """
    Build a Google OAuth consent URL for the current user.

    Args:
        current_user: Authenticated user.
        service: Injected GoogleAuthService instance.

    Returns:
        The Google authorization URL for the frontend to redirect to.
    """
    authorization_url = service.build_authorization_url(current_user)
    logger.debug("Built Google authorization URL for user %s", current_user.id)
    return GoogleAuthConnectResponse(authorization_url=authorization_url)


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    service: GoogleAuthService = Depends(_get_google_auth_service),
) -> RedirectResponse:
    """
    Handle Google's OAuth redirect (public, self-authenticating via `state`).

    Args:
        code: Authorization code from Google.
        state: Short-lived JWT identifying the connecting user.
        service: Injected GoogleAuthService instance.

    Returns:
        Redirect to the frontend settings page.

    Raises:
        HTTPException: 400 if `state` is tampered, expired, or otherwise invalid.
    """
    try:
        service.handle_callback(code=code, state=state)
    except GoogleAuthStateError as e:
        logger.warning("Google OAuth callback rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("Google account connected via OAuth callback")
    return RedirectResponse(url=f"{settings.frontend_url}/settings/youtube?connected=1")


@router.get("/status", response_model=GoogleOAuthStatusResponse)
async def status(
    current_user: CurrentUser,
    service: GoogleAuthService = Depends(_get_google_auth_service),
) -> GoogleOAuthStatusResponse:
    """
    Get the current user's Google account connection status.

    Args:
        current_user: Authenticated user.
        service: Injected GoogleAuthService instance.

    Returns:
        Connection state, account email, and token expiry.
    """
    credential = service.get_status(current_user.id)
    if credential is None:
        return GoogleOAuthStatusResponse(connected=False)

    return GoogleOAuthStatusResponse(
        connected=True,
        google_account_email=credential.google_account_email,
        token_expires_at=credential.token_expires_at,
    )


@router.delete("/disconnect", response_model=GoogleAuthDisconnectResponse)
async def disconnect(
    current_user: CurrentUser,
    service: GoogleAuthService = Depends(_get_google_auth_service),
) -> GoogleAuthDisconnectResponse:
    """
    Disconnect the current user's Google account.

    Revokes and deletes the stored credential only. Any previously synced
    playlist or transcript data is left untouched.

    Args:
        current_user: Authenticated user.
        service: Injected GoogleAuthService instance.

    Returns:
        Success message.
    """
    service.disconnect(current_user.id)
    logger.info("Google account disconnected for user %s", current_user.id)
    return GoogleAuthDisconnectResponse()
