"""API routes for Google Takeout watch-history imports."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas.watch_history import (
    WatchHistoryImportListResponse,
    WatchHistoryImportResponse,
)
from src.services import (
    InvalidTakeoutFileError,
    TakeoutFileTooLargeError,
    WatchHistoryService,
    WatchHistoryServiceError,
    get_watch_history_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_watch_history_service(db: Session = Depends(get_db)) -> WatchHistoryService:
    """Dependency that provides a WatchHistoryService instance."""
    return get_watch_history_service(db)


@router.post("/import", response_model=WatchHistoryImportResponse, status_code=201)
async def import_watch_history(
    current_user: CurrentUser,
    file: UploadFile = File(..., description="Google Takeout watch-history.json file"),
    service: WatchHistoryService = Depends(_get_watch_history_service),
) -> WatchHistoryImportResponse:
    """
    Upload and parse a Google Takeout watch-history.json export.

    Unparseable/ad rows are skipped rather than failing the whole import;
    only an unreadable/non-array file fails outright. Re-uploading a newer
    export creates an additional import record rather than replacing a
    prior one -- `plan_purge_watched` reads the union of every import
    (see `WatchHistoryRepository.list_watched_video_ids`).

    Args:
        current_user: Authenticated user.
        file: Uploaded Takeout watch-history.json file.
        service: Injected WatchHistoryService instance.

    Returns:
        The created import record, including entry_count.

    Raises:
        HTTPException: 400 if the file isn't valid Takeout JSON, 413 if it
            exceeds the size limit, 500 for any other import failure.
    """
    try:
        import_record = await service.import_watch_history(
            file=file, user_id=current_user.id
        )
    except InvalidTakeoutFileError as e:
        logger.warning("Invalid Takeout file (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except TakeoutFileTooLargeError as e:
        logger.warning("Takeout file too large (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=413, detail=str(e))
    except WatchHistoryServiceError as e:
        logger.error("Watch history import failed (user=%s): %s", current_user.id, e)
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(
        "Imported watch history %s for user=%s (%d entries)",
        import_record.id, current_user.id, import_record.entry_count,
    )
    return WatchHistoryImportResponse.model_validate(import_record)


@router.get("", response_model=WatchHistoryImportListResponse)
async def list_watch_history_imports(
    current_user: CurrentUser,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
    service: WatchHistoryService = Depends(_get_watch_history_service),
) -> WatchHistoryImportListResponse:
    """
    List the current user's past watch-history imports, most recent first.

    Args:
        current_user: Authenticated user.
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        service: Injected WatchHistoryService instance.

    Returns:
        Paginated list of watch-history imports.
    """
    imports, total = service.list_imports(
        user_id=current_user.id, skip=skip, limit=limit
    )

    items = [WatchHistoryImportResponse.model_validate(i) for i in imports]

    logger.debug(
        "Listed %d watch history imports for user %s (skip=%d, limit=%d, total=%d)",
        len(items), current_user.id, skip, limit, total,
    )

    return WatchHistoryImportListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )
