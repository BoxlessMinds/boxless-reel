"""API routes for agent-powered transcript querying."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.config import settings
from src.schemas import (
    CreateSessionRequest,
    DocumentListItem,
    DocumentResponse,
    DocumentUploadResponse,
    QueryRequest,
    QueryResponseSchema,
    SessionDetailResponse,
    SessionDocumentsResponse,
    SessionListResponse,
    SessionResponse,
)
from src.services import (
    AgentNotAvailableError,
    AgentService,
    DocumentIndexingError,
    DocumentNotFoundError,
    DocumentService,
    FileTooLargeError,
    IndexingError,
    MaxDocumentsExceededError,
    QueryExecutionError,
    SessionNotFoundError,
    TranscriptNotFoundError,
    UnsupportedFileTypeError,
    get_agent_service,
    get_document_service,
)

logger = logging.getLogger(__name__)

# Router for transcript-scoped endpoints: /api/transcripts/{id}/sessions, /api/transcripts/{id}/query
transcript_agent_router = APIRouter()

# Router for session-scoped endpoints: /api/sessions, /api/sessions/{id}
session_router = APIRouter()


def _get_agent_service(db: Session = Depends(get_db)) -> AgentService:
    """Dependency that provides AgentService instance."""
    return get_agent_service(db)


def _get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    """Dependency that provides DocumentService instance."""
    return get_document_service(db)


# =============================================================================
# Transcript-scoped endpoints (mounted at /api/transcripts)
# =============================================================================


@transcript_agent_router.post(
    "/{transcript_id}/sessions",
    response_model=SessionResponse,
    status_code=201,
)
async def create_session(
    transcript_id: str,
    request: CreateSessionRequest,
    current_user: CurrentUser,
    service: AgentService = Depends(_get_agent_service),
) -> SessionResponse:
    """
    Create a new query session for a transcript.

    Creates an agent session that maintains conversation context across
    multiple queries. The transcript is automatically indexed for vector
    search if not already indexed.

    Args:
        transcript_id: UUID of the transcript to query.
        request: Request body with optional model_provider.
        current_user: Authenticated user.
        service: Injected AgentService instance.

    Returns:
        The created session details.

    Raises:
        HTTPException: 404 if transcript not found, 500 for indexing errors,
                      503 if agent features unavailable.
    """
    try:
        session = service.create_session(
            transcript_id=transcript_id,
            user_id=current_user.id,
            model_provider=request.model_provider,
        )
        logger.info(
            "Created session %s for transcript %s (user=%s)",
            session.session_id,
            transcript_id,
            current_user.id,
        )
        return SessionResponse.model_validate(session.to_dict())

    except AgentNotAvailableError as e:
        logger.warning("Agent not available: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except TranscriptNotFoundError as e:
        logger.warning("Transcript not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except IndexingError as e:
        logger.error("Indexing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@transcript_agent_router.post(
    "/{transcript_id}/query",
    response_model=QueryResponseSchema,
)
async def query_transcript_oneshot(
    transcript_id: str,
    request: QueryRequest,
    current_user: CurrentUser,
    model_provider: Optional[str] = Query(
        None,
        description="LLM provider: 'anthropic' or 'openai'",
    ),
    service: AgentService = Depends(_get_agent_service),
) -> QueryResponseSchema:
    """
    Execute a one-shot query against a transcript.

    Answers a single question without creating a persistent session.
    Useful for quick queries where conversation context is not needed.
    The transcript is automatically indexed if not already.

    Args:
        transcript_id: UUID of the transcript to query.
        request: Request body containing the question.
        current_user: Authenticated user.
        model_provider: Optional LLM provider override.
        service: Injected AgentService instance.

    Returns:
        The agent's response with citations.

    Raises:
        HTTPException: 404 if transcript not found, 500 for query/indexing errors,
                      503 if agent features unavailable.
    """
    try:
        response = service.query_oneshot(
            transcript_id=transcript_id,
            user_id=current_user.id,
            question=request.question,
            model_provider=model_provider,
        )
        logger.info("One-shot query completed for transcript %s (user=%s)", transcript_id, current_user.id)
        return QueryResponseSchema.model_validate(response.to_dict())

    except AgentNotAvailableError as e:
        logger.warning("Agent not available: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except TranscriptNotFoundError as e:
        logger.warning("Transcript not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except IndexingError as e:
        logger.error("Indexing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except QueryExecutionError as e:
        logger.error("Query execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Session-scoped endpoints (mounted at /api/sessions)
# =============================================================================


@session_router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: CurrentUser,
    transcript_id: Optional[str] = Query(
        None,
        description="Filter by transcript ID",
    ),
    service: AgentService = Depends(_get_agent_service),
) -> SessionListResponse:
    """
    List all active query sessions for the current user.

    Args:
        current_user: Authenticated user.
        transcript_id: Optional filter by transcript ID.
        service: Injected AgentService instance.

    Returns:
        List of active sessions with total count.
    """
    sessions = service.list_sessions(user_id=current_user.id, transcript_id=transcript_id)
    items = [SessionResponse.model_validate(s.to_dict()) for s in sessions]

    logger.debug("Listed %d sessions for user %s", len(items), current_user.id)
    return SessionListResponse(items=items, total=len(items))


@session_router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    service: AgentService = Depends(_get_agent_service),
) -> SessionDetailResponse:
    """
    Get session details with conversation history.

    Args:
        session_id: UUID of the session.
        current_user: Authenticated user.
        service: Injected AgentService instance.

    Returns:
        Session details including full message history.

    Raises:
        HTTPException: 404 if session not found or not owned by user.
    """
    try:
        session = service.get_session(session_id, user_id=current_user.id)
        history = service.get_session_history(session_id, user_id=current_user.id)

        session_dict = session.to_dict()
        session_dict["messages"] = history

        logger.debug("Retrieved session %s with %d messages (user=%s)", session_id, len(history), current_user.id)
        return SessionDetailResponse.model_validate(session_dict)

    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))


@session_router.post("/{session_id}/query", response_model=QueryResponseSchema)
async def query_session(
    session_id: str,
    request: QueryRequest,
    current_user: CurrentUser,
    service: AgentService = Depends(_get_agent_service),
) -> QueryResponseSchema:
    """
    Execute a query within an existing session.

    Maintains conversation context from previous queries in the session.
    Follow-up questions can reference earlier parts of the conversation.

    Args:
        session_id: UUID of the session.
        request: Request body containing the question.
        current_user: Authenticated user.
        service: Injected AgentService instance.

    Returns:
        The agent's response with citations.

    Raises:
        HTTPException: 404 if session not found or not owned by user, 500 for query errors.
    """
    try:
        response = service.query(
            session_id=session_id,
            user_id=current_user.id,
            question=request.question,
        )
        logger.info("Query completed for session %s (user=%s)", session_id, current_user.id)
        return QueryResponseSchema.model_validate(response.to_dict())

    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except QueryExecutionError as e:
        logger.error("Query execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@session_router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: CurrentUser,
    service: AgentService = Depends(_get_agent_service),
) -> dict:
    """
    Delete a query session.

    Removes the session from the active registry. Note that conversation
    history stored in the agent's database may be retained.

    Args:
        session_id: UUID of the session to delete.
        current_user: Authenticated user.
        service: Injected AgentService instance.

    Returns:
        Success message.

    Raises:
        HTTPException: 404 if session not found or not owned by user.
    """
    try:
        service.delete_session(session_id, user_id=current_user.id)
        logger.info("Deleted session %s (user=%s)", session_id, current_user.id)
        return {"message": "Session deleted successfully"}

    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Session Document endpoints (mounted at /api/sessions)
# =============================================================================


@session_router.post(
    "/{session_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_session_document(
    session_id: str,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="Document file to upload"),
    agent_service: AgentService = Depends(_get_agent_service),
    document_service: DocumentService = Depends(_get_document_service),
) -> DocumentUploadResponse:
    """
    Upload a document to a session.

    Supported file types: PDF, DOCX, TXT, MD.
    Maximum 5 documents per session.
    Size limits: 10MB for PDF/DOCX, 5MB for TXT/MD.

    Args:
        session_id: UUID of the session.
        current_user: Authenticated user.
        file: Uploaded file.
        agent_service: Injected AgentService instance.
        document_service: Injected DocumentService instance.

    Returns:
        The uploaded document details.

    Raises:
        HTTPException: 404 if session not found, 400 for validation errors,
                      413 if file too large, 500 for processing errors.
    """
    # Verify session exists and belongs to user
    try:
        agent_service.get_session(session_id, user_id=current_user.id)
    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))

    # Upload document
    try:
        document = await document_service.upload_document(
            file=file,
            session_id=session_id,
            user_id=current_user.id,
        )
        logger.info(
            "Uploaded document %s to session %s (user=%s)",
            document.id,
            session_id,
            current_user.id,
        )
        return DocumentUploadResponse(
            document=DocumentResponse.model_validate(document),
            message="Document uploaded successfully",
        )

    except MaxDocumentsExceededError as e:
        logger.warning("Max documents exceeded: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except UnsupportedFileTypeError as e:
        logger.warning("Unsupported file type: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except FileTooLargeError as e:
        logger.warning("File too large: %s", e)
        raise HTTPException(status_code=413, detail=str(e))
    except DocumentIndexingError as e:
        logger.error("Document indexing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@session_router.get("/{session_id}/documents", response_model=SessionDocumentsResponse)
async def list_session_documents(
    session_id: str,
    current_user: CurrentUser,
    agent_service: AgentService = Depends(_get_agent_service),
    document_service: DocumentService = Depends(_get_document_service),
) -> SessionDocumentsResponse:
    """
    List all documents for a session.

    Args:
        session_id: UUID of the session.
        current_user: Authenticated user.
        agent_service: Injected AgentService instance.
        document_service: Injected DocumentService instance.

    Returns:
        List of documents in the session.

    Raises:
        HTTPException: 404 if session not found.
    """
    # Verify session exists and belongs to user
    try:
        agent_service.get_session(session_id, user_id=current_user.id)
    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))

    documents = document_service.list_session_documents(session_id, user_id=current_user.id)
    items = [DocumentListItem.model_validate(doc) for doc in documents]
    can_add = document_service.can_add_document(session_id)

    logger.debug(
        "Listed %d documents for session %s (user=%s)",
        len(items),
        session_id,
        current_user.id,
    )

    return SessionDocumentsResponse(
        session_id=session_id,
        documents=items,
        count=len(items),
        max_documents=settings.max_documents_per_session,
        can_add_more=can_add,
    )


@session_router.delete("/{session_id}/documents/{document_id}")
async def delete_session_document(
    session_id: str,
    document_id: str,
    current_user: CurrentUser,
    agent_service: AgentService = Depends(_get_agent_service),
    document_service: DocumentService = Depends(_get_document_service),
) -> dict:
    """
    Delete a document from a session.

    Args:
        session_id: UUID of the session.
        document_id: UUID of the document.
        current_user: Authenticated user.
        agent_service: Injected AgentService instance.
        document_service: Injected DocumentService instance.

    Returns:
        Success message.

    Raises:
        HTTPException: 404 if session or document not found.
    """
    # Verify session exists and belongs to user
    try:
        agent_service.get_session(session_id, user_id=current_user.id)
    except SessionNotFoundError as e:
        logger.warning("Session not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))

    # Delete document
    try:
        document_service.delete_document(document_id, user_id=current_user.id)
        logger.info(
            "Deleted document %s from session %s (user=%s)",
            document_id,
            session_id,
            current_user.id,
        )
        return {"message": "Document deleted successfully"}

    except DocumentNotFoundError as e:
        logger.warning("Document not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
