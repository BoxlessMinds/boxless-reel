"""Pydantic schemas for authentication."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=6, description="User's password")


class TokenResponse(BaseModel):
    """Token response after successful authentication."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token for obtaining new access tokens")
    token_type: str = Field(default="bearer", description="Token type")


class RefreshTokenRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str = Field(..., description="Refresh token")


class RegisterRequest(BaseModel):
    """Registration request, optionally with invitation token."""

    token: Optional[str] = Field(None, description="Invitation token (required when invitation mode is active)")
    email: EmailStr = Field(..., description="Email address (must match invitation when using token)")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name")


class UserResponse(BaseModel):
    """User profile response."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="Email address")
    display_name: str = Field(..., description="Display name")
    role: str = Field(..., description="User role (admin or user)")
    is_active: bool = Field(..., description="Whether user is active")
    created_at: datetime = Field(..., description="Account creation time")

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """User profile update request."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Display name")
    current_password: Optional[str] = Field(None, min_length=1, description="Required when changing password")
    new_password: Optional[str] = Field(None, min_length=8, description="New password")


class AdminUserUpdateRequest(BaseModel):
    """Admin user update request."""

    is_active: Optional[bool] = Field(None, description="Whether user is active")
    role: Optional[str] = Field(None, pattern="^(admin|user)$", description="User role")


class UserListResponse(BaseModel):
    """Paginated list of users."""

    users: list[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")


class InvitationCreateRequest(BaseModel):
    """Create invitation request."""

    email: EmailStr = Field(..., description="Email to invite")


class InvitationResponse(BaseModel):
    """Invitation response."""

    id: str = Field(..., description="Invitation ID")
    email: str = Field(..., description="Invited email")
    token: Optional[str] = Field(None, description="Invitation token (only for pending invitations)")
    status: str = Field(..., description="Invitation status")
    expires_at: datetime = Field(..., description="Expiration time")
    created_at: datetime = Field(..., description="Creation time")

    model_config = {"from_attributes": True}


class InvitationListResponse(BaseModel):
    """List of invitations."""

    invitations: list[InvitationResponse] = Field(..., description="List of invitations")
    total: int = Field(..., description="Total count")


class InvitationValidateResponse(BaseModel):
    """Response when validating an invitation token."""

    valid: bool = Field(..., description="Whether token is valid")
    email: Optional[str] = Field(None, description="Email for the invitation")
    expires_at: Optional[datetime] = Field(None, description="Expiration time")
    error: Optional[str] = Field(None, description="Error message if invalid")


class ValidateTokenRequest(BaseModel):
    """Request body for invitation token validation."""

    token: str = Field(..., description="Invitation token to validate")


class BulkInvitationRequest(BaseModel):
    """Bulk invitation request for admin."""

    emails: list[EmailStr] = Field(..., min_length=1, max_length=50, description="List of emails to invite")


class BulkInvitationResponse(BaseModel):
    """Response for bulk invitation."""

    created: list[str] = Field(..., description="Successfully created invitations")
    failed: list[dict] = Field(..., description="Failed invitations with reasons")


class RegistrationModeResponse(BaseModel):
    """Public response indicating current registration mode."""

    require_invitation: bool = Field(..., description="Whether invitation is required to register")


class RegistrationModeUpdateRequest(BaseModel):
    """Admin request to update registration mode."""

    require_invitation: bool = Field(..., description="Whether invitation should be required")
