"""API routes for playlist sync and library view operations."""

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    PlaylistItemListResponse,
    PlaylistItemResponse,
    PlaylistListResponse,
    PlaylistResponse,
    QuotaResponse,
    SyncResponse,
)
from src.services import (
    GoogleAuthServiceError,
    GoogleCredentialNotFoundError,
    GoogleTokenRefreshError,
    PlaylistSyncService,
    QuotaExceededError,
    QuotaService,
    YouTubeDataServiceError,
    get_playlist_sync_service,
    get_quota_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service(db: Session = Depends(get_db)) -> PlaylistSyncService:
    """Dependency that provides PlaylistSyncService instance."""
    return get_playlist_sync_service(db)


def _get_quota_service(db: Session = Depends(get_db)) -> QuotaService:
    """Dependency that provides QuotaService instance."""
    return get_quota_service(db)


@router.post("/sync", response_model=SyncResponse)
async def sync_playlists(
    current_user: CurrentUser,
    service: PlaylistSyncService = Depends(_get_service),
) -> SyncResponse:
    """
    Full re-sync of the current user's owned YouTube playlists into the local cache.

    Args:
        current_user: Authenticated user.
        service: Injected PlaylistSyncService instance.

    Returns:
        Summary of the sync run (counts and quota units spent).

    Raises:
        HTTPException: 400 if no Google account is connected, 401 if the
            connected account's credentials could not be refreshed, 502 for
            other Google auth service errors.
    """
    try:
        result = service.sync_owned_playlists(current_user.id)
        logger.info(
            "Synced playlists for user=%s: %s playlists, %s items, %s quota units",
            current_user.id, result.playlists_synced, result.items_synced, result.quota_units_used,
        )
        return SyncResponse(
            playlists_synced=result.playlists_synced,
            items_synced=result.items_synced,
            quota_units_used=result.quota_units_used,
            synced_at=result.synced_at,
        )
    except GoogleCredentialNotFoundError as e:
        logger.warning("Sync attempted with no connected Google account (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleTokenRefreshError as e:
        logger.warning("Sync failed - could not refresh Google credentials (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=401, detail=str(e))
    except GoogleAuthServiceError as e:
        logger.error("Sync failed - Google auth service error (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=str(e))
    except QuotaExceededError as e:
        logger.error("Sync failed - YouTube Data API quota exhausted (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=429, detail=str(e))
    except YouTubeDataServiceError as e:
        logger.error("Sync failed - YouTube Data API error (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("", response_model=PlaylistListResponse)
async def list_playlists(
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: PlaylistSyncService = Depends(_get_service),
) -> PlaylistListResponse:
    """
    List cached playlists for the current user, with duplicate/unavailable counts.

    Args:
        current_user: Authenticated user.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        service: Injected PlaylistSyncService instance.

    Returns:
        Paginated list of playlists with computed counts.
    """
    skip = (page - 1) * page_size
    rows, total = service.list_playlists(current_user.id, skip=skip, limit=page_size)

    items = [
        PlaylistResponse(
            id=playlist.id,
            youtube_playlist_id=playlist.youtube_playlist_id,
            title=playlist.title,
            description=playlist.description,
            privacy_status=playlist.privacy_status,
            item_count=playlist.item_count,
            duplicate_count=duplicate_count,
            unavailable_count=unavailable_count,
            is_owned=playlist.is_owned,
            last_synced_at=playlist.last_synced_at,
        )
        for playlist, duplicate_count, unavailable_count in rows
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PlaylistListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{playlist_id}/items", response_model=PlaylistItemListResponse)
async def list_playlist_items(
    playlist_id: str,
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: PlaylistSyncService = Depends(_get_service),
) -> PlaylistItemListResponse:
    """
    List cached items for a single playlist owned by the current user.

    Args:
        playlist_id: UUID of the playlist.
        current_user: Authenticated user.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        service: Injected PlaylistSyncService instance.

    Returns:
        Paginated list of playlist items.

    Raises:
        HTTPException: 404 if the playlist does not exist or is not owned by
            the current user.
    """
    skip = (page - 1) * page_size
    result = service.get_playlist_items(playlist_id, current_user.id, skip=skip, limit=page_size)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Playlist not found: {playlist_id}")

    playlist_items, total = result
    items = [PlaylistItemResponse.model_validate(item) for item in playlist_items]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PlaylistItemListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/quota", response_model=QuotaResponse)
async def get_quota_status(
    current_user: CurrentUser,
    service: QuotaService = Depends(_get_quota_service),
) -> QuotaResponse:
    """
    Get the shared, app-wide YouTube Data API daily quota status.

    Pinned to this path (rather than a bare `/api/quota`) per
    `CONTEXT/story-config.yaml`'s `quota.quota_endpoint` — the quota pool is
    global across all users, not a fictional per-user allowance.

    Args:
        current_user: Authenticated user (auth-gated, but the figures
            returned are global, not scoped to this user).
        service: Injected QuotaService instance.

    Returns:
        Daily limit, units used today (Pacific time), and units remaining.
    """
    status = service.get_daily_quota_status()
    return QuotaResponse(
        daily_limit=status.daily_limit,
        used=status.used,
        remaining=status.remaining,
    )
