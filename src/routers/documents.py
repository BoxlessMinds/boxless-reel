"""API routes for document management."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.dependencies.auth import CurrentUser
from src.schemas import (
    DocumentListItem,
    DocumentListResponse,
    DocumentResponse,
)
from src.services import (
    DocumentNotFoundError,
    DocumentService,
    get_document_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    """Dependency that provides DocumentService instance."""
    return get_document_service(db)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: CurrentUser,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
    service: DocumentService = Depends(_get_document_service),
) -> DocumentListResponse:
    """
    List all documents for the current user with pagination.

    Args:
        current_user: Authenticated user.
        skip: Number of records to skip.
        limit: Maximum number of records to return.
        service: Injected DocumentService instance.

    Returns:
        Paginated list of documents.
    """
    documents, total = service.list_user_documents(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )

    items = [DocumentListItem.model_validate(doc) for doc in documents]

    logger.debug(
        "Listed %d documents for user %s (skip=%d, limit=%d, total=%d)",
        len(items),
        current_user.id,
        skip,
        limit,
        total,
    )

    return DocumentListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: CurrentUser,
    service: DocumentService = Depends(_get_document_service),
) -> DocumentResponse:
    """
    Get a document by ID.

    Args:
        document_id: UUID of the document.
        current_user: Authenticated user.
        service: Injected DocumentService instance.

    Returns:
        Document details.

    Raises:
        HTTPException: 404 if document not found.
    """
    try:
        document = service.get_document(document_id, user_id=current_user.id)
        logger.debug("Retrieved document %s for user %s", document_id, current_user.id)
        return DocumentResponse.model_validate(document)

    except DocumentNotFoundError as e:
        logger.warning("Document not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
