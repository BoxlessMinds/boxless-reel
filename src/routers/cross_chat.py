"""API routes for cross-chat multi-transcript querying."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas.cross_chat import (
    CreateCrossChatSessionRequest,
    CrossChatCitationResponse,
    CrossChatMessageResponse,
    CrossChatQueryRequest,
    CrossChatQueryResponse,
    CrossChatSessionDetailResponse,
    CrossChatSessionListResponse,
    CrossChatSessionResponse,
    SessionSummary,
)
from src.services import (
    AgentNotAvailableError,
    CrossChatService,
    CrossChatSessionNotFoundError,
    CrossChatValidationError,
    IndexingError,
    QueryExecutionError,
    get_cross_chat_service,
)

logger = logging.getLogger(__name__)

cross_chat_router = APIRouter()


def _get_cross_chat_service(db: Session = Depends(get_db)) -> CrossChatService:
    """Dependency that provides CrossChatService instance."""
    return get_cross_chat_service(db)


def _build_session_response(db_session) -> CrossChatSessionResponse:
    """Build a CrossChatSessionResponse from a database model."""
    referenced = []
    for ref in db_session.referenced_sessions:
        if ref.session and ref.session.transcript:
            transcript = ref.session.transcript
            referenced.append(
                SessionSummary(
                    session_id=ref.session_id,
                    transcript_id=str(transcript.id),
                    video_id=transcript.video_id,
                    video_title=transcript.title,
                    thumbnail_url=transcript.thumbnail_url,
                )
            )

    query_count = 0
    if db_session.messages:
        query_count = sum(1 for m in db_session.messages if m.role == "user")

    return CrossChatSessionResponse(
        id=db_session.id,
        referenced_sessions=referenced,
        model_provider=db_session.model_provider,
        model_name=db_session.model_name,
        created_at=db_session.created_at,
        last_activity=db_session.updated_at,
        query_count=query_count,
    )


def _build_detail_response(db_session) -> CrossChatSessionDetailResponse:
    """Build a CrossChatSessionDetailResponse from a database model."""
    base = _build_session_response(db_session)

    messages = []
    if db_session.messages:
        for msg in db_session.messages:
            citations = None
            if msg.citations:
                citations = [CrossChatCitationResponse(**c) for c in msg.citations]
            messages.append(
                CrossChatMessageResponse(
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.created_at,
                    citations=citations,
                )
            )

    return CrossChatSessionDetailResponse(
        id=base.id,
        referenced_sessions=base.referenced_sessions,
        model_provider=base.model_provider,
        model_name=base.model_name,
        created_at=base.created_at,
        last_activity=base.last_activity,
        query_count=base.query_count,
        messages=messages,
    )


@cross_chat_router.post(
    "/sessions",
    response_model=CrossChatSessionResponse,
    status_code=201,
)
async def create_cross_chat_session(
    request: CreateCrossChatSessionRequest,
    current_user: CurrentUser,
    service: CrossChatService = Depends(_get_cross_chat_service),
) -> CrossChatSessionResponse:
    """
    Create a new cross-chat session spanning multiple transcripts.

    Requires at least 2 valid agent session IDs. All sessions must
    belong to the current user.

    Args:
        request: Request body with session_ids and optional model_provider.
        current_user: Authenticated user.
        service: Injected CrossChatService instance.

    Returns:
        The created cross-chat session details.
    """
    try:
        db_session = service.create_session(
            session_ids=request.session_ids,
            user_id=current_user.id,
            model_provider=request.model_provider,
        )
        logger.info(
            "Created cross-chat session %s (user=%s)",
            db_session.id,
            current_user.id,
        )
        return _build_session_response(db_session)

    except AgentNotAvailableError as e:
        logger.warning("Agent not available: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except CrossChatValidationError as e:
        logger.warning("Cross-chat validation failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except IndexingError as e:
        logger.error("Indexing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@cross_chat_router.get(
    "/sessions",
    response_model=CrossChatSessionListResponse,
)
async def list_cross_chat_sessions(
    current_user: CurrentUser,
    service: CrossChatService = Depends(_get_cross_chat_service),
) -> CrossChatSessionListResponse:
    """
    List all cross-chat sessions for the current user.

    Args:
        current_user: Authenticated user.
        service: Injected CrossChatService instance.

    Returns:
        List of cross-chat sessions with total count.
    """
    db_sessions = service.list_sessions(user_id=current_user.id)
    items = [_build_session_response(s) for s in db_sessions]
    logger.debug("Listed %d cross-chat sessions for user %s", len(items), current_user.id)
    return CrossChatSessionListResponse(items=items, total=len(items))


@cross_chat_router.get(
    "/sessions/{cross_chat_id}",
    response_model=CrossChatSessionDetailResponse,
)
async def get_cross_chat_session(
    cross_chat_id: str,
    current_user: CurrentUser,
    service: CrossChatService = Depends(_get_cross_chat_service),
) -> CrossChatSessionDetailResponse:
    """
    Get a cross-chat session with full conversation history.

    Args:
        cross_chat_id: UUID of the cross-chat session.
        current_user: Authenticated user.
        service: Injected CrossChatService instance.

    Returns:
        Cross-chat session details with messages.
    """
    try:
        db_session = service.get_session(cross_chat_id, user_id=current_user.id)
        logger.debug("Retrieved cross-chat session %s (user=%s)", cross_chat_id, current_user.id)
        return _build_detail_response(db_session)

    except CrossChatSessionNotFoundError as e:
        logger.warning("Cross-chat session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))


@cross_chat_router.post(
    "/sessions/{cross_chat_id}/query",
    response_model=CrossChatQueryResponse,
)
async def query_cross_chat_session(
    cross_chat_id: str,
    request: CrossChatQueryRequest,
    current_user: CurrentUser,
    service: CrossChatService = Depends(_get_cross_chat_service),
) -> CrossChatQueryResponse:
    """
    Execute a query across all transcripts in a cross-chat session.

    Args:
        cross_chat_id: UUID of the cross-chat session.
        request: Request body containing the question.
        current_user: Authenticated user.
        service: Injected CrossChatService instance.

    Returns:
        The agent response with cross-transcript citations.
    """
    try:
        result = service.query(
            cross_chat_id=cross_chat_id,
            user_id=current_user.id,
            question=request.question,
        )
        logger.info(
            "Cross-chat query completed for session %s (user=%s)",
            cross_chat_id,
            current_user.id,
        )
        return CrossChatQueryResponse(
            content=result["content"],
            citations=[CrossChatCitationResponse(**c) for c in result["citations"]],
            session_id=result["session_id"],
            model_used=result["model_used"],
            search_results_used=result["search_results_used"],
            created_at=result["created_at"],
        )

    except CrossChatSessionNotFoundError as e:
        logger.warning("Cross-chat session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except QueryExecutionError as e:
        logger.error("Cross-chat query failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@cross_chat_router.delete("/sessions/{cross_chat_id}")
async def delete_cross_chat_session(
    cross_chat_id: str,
    current_user: CurrentUser,
    service: CrossChatService = Depends(_get_cross_chat_service),
) -> dict:
    """
    Delete a cross-chat session.

    Args:
        cross_chat_id: UUID of the cross-chat session to delete.
        current_user: Authenticated user.
        service: Injected CrossChatService instance.

    Returns:
        Success message.
    """
    try:
        service.delete_session(cross_chat_id, user_id=current_user.id)
        logger.info(
            "Deleted cross-chat session %s (user=%s)",
            cross_chat_id,
            current_user.id,
        )
        return {"message": "Cross-chat session deleted successfully"}

    except CrossChatSessionNotFoundError as e:
        logger.warning("Cross-chat session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
