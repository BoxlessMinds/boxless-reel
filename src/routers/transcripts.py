"""API routes for transcript operations."""

import logging
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    TranscriptExtractRequest,
    TranscriptListItem,
    TranscriptListResponse,
    TranscriptResponse,
)
from src.services import (
    AgentService,
    InvalidVideoIdError,
    TranscriptAlreadyExistsError,
    TranscriptNotAvailableError,
    TranscriptService,
    VideoNotFoundError,
    YouTubeServiceError,
    get_agent_service,
    get_transcript_service,
)
from src.services.exceptions import AgentNotAvailableError, IndexingError

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service(db: Session = Depends(get_db)) -> TranscriptService:
    """Dependency that provides TranscriptService instance."""
    return get_transcript_service(db)


def _get_agent_service(db: Session = Depends(get_db)) -> AgentService:
    """Dependency that provides AgentService instance."""
    return get_agent_service(db)


@router.post("/extract", response_model=TranscriptResponse, status_code=201)
async def extract_transcript(
    request: TranscriptExtractRequest,
    current_user: CurrentUser,
    service: TranscriptService = Depends(_get_service),
    agent_service: AgentService = Depends(_get_agent_service),
) -> TranscriptResponse:
    """
    Extract transcript from a YouTube video and save to database.

    Args:
        request: Request body containing YouTube URL.
        current_user: Authenticated user.
        service: Injected TranscriptService instance.
        agent_service: Injected AgentService instance for indexing.

    Returns:
        The extracted transcript details.

    Raises:
        HTTPException: 400 for invalid URL, 404 for unavailable video/transcript,
                      409 for duplicate video, 500 for service errors.
    """
    try:
        transcript = service.extract_and_save(request.youtube_url, user_id=current_user.id)
        logger.info("Successfully extracted transcript for video: %s (user=%s)", transcript.video_id, current_user.id)

        # Index for agent queries (best-effort, don't fail extraction)
        try:
            chunk_count = agent_service.index_transcript(str(transcript.id), user_id=current_user.id)
            logger.info("Indexed transcript %s with %s chunks", transcript.id, chunk_count)
        except AgentNotAvailableError:
            logger.warning("Agent not available - transcript %s not indexed", transcript.id)
        except IndexingError as e:
            logger.warning("Failed to index transcript %s: %s", transcript.id, e)

        return TranscriptResponse.model_validate(transcript)
    except TranscriptAlreadyExistsError as e:
        logger.warning("Duplicate transcript attempt: %s", e)
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidVideoIdError as e:
        logger.warning("Invalid video ID/URL: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except VideoNotFoundError as e:
        logger.warning("Video not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except TranscriptNotAvailableError as e:
        logger.warning("Transcript not available: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except YouTubeServiceError as e:
        logger.error("YouTube service error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=TranscriptListResponse)
async def list_transcripts(
    current_user: CurrentUser,
    search: Optional[str] = Query(None, description="Search in title and transcript text"),
    language: Optional[str] = Query(None, description="Filter by language code"),
    start_date: Optional[datetime] = Query(None, description="Filter by created_at >= this date"),
    end_date: Optional[datetime] = Query(None, description="Filter by created_at <= this date"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: TranscriptService = Depends(_get_service),
) -> TranscriptListResponse:
    """
    List transcripts for the current user with optional filtering and pagination.

    Args:
        current_user: Authenticated user.
        search: Search term for title/content.
        language: Language code filter.
        start_date: Minimum created_at date.
        end_date: Maximum created_at date.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        service: Injected TranscriptService instance.

    Returns:
        Paginated list of transcripts with metadata.
    """
    skip = (page - 1) * page_size

    transcripts, total = service.list_transcripts(
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
        search=search,
        language=language,
        start_date=start_date,
        end_date=end_date,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    items = [TranscriptListItem.model_validate(t) for t in transcripts]

    return TranscriptListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(
    transcript_id: str,
    current_user: CurrentUser,
    service: TranscriptService = Depends(_get_service),
) -> TranscriptResponse:
    """
    Get a single transcript by ID.

    Args:
        transcript_id: UUID of the transcript.
        current_user: Authenticated user.
        service: Injected TranscriptService instance.

    Returns:
        The transcript details.

    Raises:
        HTTPException: 404 if transcript not found or not owned by user.
    """
    transcript = service.get_transcript(transcript_id, user_id=current_user.id)

    if transcript is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found: {transcript_id}"
        )

    return TranscriptResponse.model_validate(transcript)


@router.delete("/{transcript_id}")
async def delete_transcript(
    transcript_id: str,
    current_user: CurrentUser,
    service: TranscriptService = Depends(_get_service),
) -> dict:
    """
    Delete a transcript by ID.

    Args:
        transcript_id: UUID of the transcript to delete.
        current_user: Authenticated user.
        service: Injected TranscriptService instance.

    Returns:
        Success message.

    Raises:
        HTTPException: 404 if transcript not found or not owned by user.
    """
    deleted = service.delete_transcript(transcript_id, user_id=current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found: {transcript_id}"
        )

    logger.info("Deleted transcript: %s (user=%s)", transcript_id, current_user.id)
    return {"message": "Transcript deleted successfully"}
