"""Pydantic schemas for Google OAuth (YouTube account connection) API."""

from datetime import datetime

from pydantic import BaseModel, Field


class GoogleAuthConnectResponse(BaseModel):
    """Response containing the Google consent URL to redirect the user to."""

    authorization_url: str = Field(description="Google OAuth consent screen URL")


class GoogleOAuthStatusResponse(BaseModel):
    """Connection status for the current user's Google account."""

    connected: bool = Field(description="Whether the user has a connected Google account")
    google_account_email: str | None = Field(
        default=None, description="Connected Google account email, if connected"
    )
    token_expires_at: datetime | None = Field(
        default=None, description="Current access token expiry, if connected"
    )


class GoogleAuthDisconnectResponse(BaseModel):
    """Response after successfully disconnecting a Google account."""

    message: str = Field(default="Google account disconnected successfully")
