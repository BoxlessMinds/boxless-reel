"""API router for settings endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    ValidateKeyRequest,
    ValidateKeyResponse,
)
from src.services import SettingsService, get_settings_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service(db: Session = Depends(get_db)) -> SettingsService:
    """Dependency injection for SettingsService."""
    return get_settings_service(db)


@router.get("", response_model=LLMSettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    service: SettingsService = Depends(_get_service),
) -> LLMSettingsResponse:
    """
    Get current LLM settings for the authenticated user.

    Returns all settings with API key status (configured/not configured).
    Actual API key values are never exposed.
    """
    logger.debug("Getting settings for user %s", current_user.id)
    data = service.get_settings_response_data(user_id=current_user.id)
    return LLMSettingsResponse(**data)


@router.put("", response_model=LLMSettingsResponse)
async def update_settings(
    request: LLMSettingsUpdate,
    current_user: CurrentUser,
    service: SettingsService = Depends(_get_service),
) -> LLMSettingsResponse:
    """
    Update LLM settings for the authenticated user.

    Only provided fields are updated. Use None to skip a field,
    or empty string to clear an API key.
    """
    logger.info("Updating settings for user %s", current_user.id)

    # Convert request to dict for update
    update_data = request.model_dump(exclude_none=True)
    service.update_settings(update_data, user_id=current_user.id)

    # Return updated settings
    data = service.get_settings_response_data(user_id=current_user.id)
    return LLMSettingsResponse(**data)


@router.post("/validate-key", response_model=ValidateKeyResponse)
async def validate_api_key(
    request: ValidateKeyRequest,
    current_user: CurrentUser,
    service: SettingsService = Depends(_get_service),
) -> ValidateKeyResponse:
    """
    Validate an API key before saving.

    Makes a minimal API call to verify the key works.
    """
    logger.info("Validating %s API key for user %s", request.provider, current_user.id)

    loop = asyncio.get_event_loop()
    is_valid, error = await loop.run_in_executor(
        None, lambda: service.validate_api_key(request.provider, request.api_key)
    )

    return ValidateKeyResponse(valid=is_valid, error=error)
