"""API routes for authentication."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegistrationModeResponse,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from src.services import (
    AuthenticationError,
    AuthService,
    InvalidInvitationError,
    SystemSettingsService,
    TokenError,
    UserExistsError,
    UserService,
    get_auth_service,
    get_system_settings_service,
    get_user_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Dependency injection for AuthService."""
    return get_auth_service(db)


def _get_user_service(db: Session = Depends(get_db)) -> UserService:
    """Dependency injection for UserService."""
    return get_user_service(db)


def _get_system_settings_service(db: Session = Depends(get_db)) -> SystemSettingsService:
    """Dependency injection for SystemSettingsService."""
    return get_system_settings_service(db)


@router.get("/registration-mode", response_model=RegistrationModeResponse)
async def get_registration_mode(
    system_settings: SystemSettingsService = Depends(_get_system_settings_service),
) -> RegistrationModeResponse:
    """
    Get current registration mode (public endpoint).

    Returns:
        Whether invitation is required to register.
    """
    return RegistrationModeResponse(
        require_invitation=system_settings.is_invitation_required()
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """
    Authenticate user and return tokens.

    Args:
        request: Login credentials.
        auth_service: Injected AuthService.

    Returns:
        Access and refresh tokens.

    Raises:
        HTTPException: 401 if credentials invalid.
    """
    try:
        user, access_token, refresh_token = auth_service.authenticate(
            email=request.email,
            password=request.password,
        )
        logger.info("User %s logged in successfully", user.email)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    except AuthenticationError as e:
        logger.warning("Login failed for %s: %s", request.email, e)
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: RegisterRequest,
    user_service: UserService = Depends(_get_user_service),
    system_settings: SystemSettingsService = Depends(_get_system_settings_service),
) -> UserResponse:
    """
    Register a new user, with or without an invitation token.

    When invitation mode is active, a valid invitation token is required.
    When open registration is enabled, users can register without a token.
    If a token is provided during open registration, the invitation flow is used.

    Args:
        request: Registration data, optionally with invitation token.
        user_service: Injected UserService.
        system_settings: Injected SystemSettingsService.

    Returns:
        Created user profile.

    Raises:
        HTTPException: 400 if invitation invalid or required but missing, 409 if user exists.
    """
    invitation_required = system_settings.is_invitation_required()

    try:
        if request.token:
            # Token provided: use invitation flow regardless of mode
            user = user_service.register_from_invitation(
                token=request.token,
                email=request.email,
                password=request.password,
                display_name=request.display_name,
            )
        elif invitation_required:
            # No token but invitation is required
            raise HTTPException(
                status_code=400,
                detail="Invitation token is required for registration",
            )
        else:
            # Open registration: no token needed
            user = user_service.register_open(
                email=request.email,
                password=request.password,
                display_name=request.display_name,
            )

        logger.info("User %s registered successfully", user.email)
        return UserResponse.model_validate(user)
    except InvalidInvitationError as e:
        logger.warning("Registration failed - invalid invitation: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except UserExistsError as e:
        logger.warning("Registration failed - user exists: %s", e)
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """
    Refresh access token using refresh token.

    Args:
        request: Refresh token.
        auth_service: Injected AuthService.

    Returns:
        New access and refresh tokens.

    Raises:
        HTTPException: 401 if refresh token invalid.
    """
    try:
        access_token, refresh_token = auth_service.refresh_tokens(request.refresh_token)
        logger.debug("Tokens refreshed successfully")
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    except TokenError as e:
        logger.warning("Token refresh failed: %s", e)
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> dict:
    """
    Logout by revoking refresh token.

    Args:
        request: Refresh token to revoke.
        auth_service: Injected AuthService.

    Returns:
        Success message.
    """
    auth_service.logout(request.refresh_token)
    logger.debug("User logged out")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: CurrentUser,
) -> UserResponse:
    """
    Get current user's profile.

    Args:
        current_user: Authenticated user from token.

    Returns:
        User profile.
    """
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    request: UserUpdateRequest,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    """
    Update current user's profile.

    Args:
        request: Fields to update.
        current_user: Authenticated user from token.
        auth_service: Injected AuthService.

    Returns:
        Updated user profile.

    Raises:
        HTTPException: 401 if current password is incorrect, 404 if user not found.
    """
    try:
        updated_user = auth_service.update_profile(
            user_id=current_user.id,
            display_name=request.display_name,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    # Revoke all refresh tokens on password change for security
    if request.new_password:
        auth_service.logout_all_sessions(str(current_user.id))
        logger.info("Revoked all tokens for user %s after password change", current_user.email)

    logger.info("User %s updated profile", current_user.email)
    return UserResponse.model_validate(updated_user)
