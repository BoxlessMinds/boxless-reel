"""Repository for document database operations."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import settings
from src.models.document import Document

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Data access layer for document operations."""

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(self, document: Document) -> Document:
        """
        Create a new document record.

        Args:
            document: Document model instance to persist.

        Returns:
            The persisted document with generated ID.
        """
        logger.debug("Creating document: %s", document.original_filename)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        logger.debug("Created document with id: %s", document.id)
        return document

    def get_by_id(
        self,
        document_id: UUID | str,
        user_id: str | None = None,
    ) -> Document | None:
        """
        Get a document by its ID.

        Args:
            document_id: UUID of the document.
            user_id: Optional user ID to filter by ownership.

        Returns:
            Document if found, None otherwise.
        """
        logger.debug("Fetching document by id: %s (user_id=%s)", document_id, user_id)
        stmt = select(Document).where(Document.id == str(document_id))
        if user_id:
            stmt = stmt.where(Document.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Document not found: %s", document_id)
        return result

    def list_by_session(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> list[Document]:
        """
        List all documents for a session.

        Args:
            session_id: UUID of the session.
            user_id: Optional user ID to filter by ownership.

        Returns:
            List of documents for the session.
        """
        logger.debug("Listing documents for session: %s", session_id)
        stmt = select(Document).where(Document.session_id == session_id)
        if user_id:
            stmt = stmt.where(Document.user_id == user_id)
        stmt = stmt.order_by(Document.created_at.desc())
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d documents for session %s", len(results), session_id)
        return results

    def list_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Document]:
        """
        List all documents for a user with pagination.

        Args:
            user_id: UUID of the user.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of documents owned by the user.
        """
        logger.debug("Listing documents for user: %s (skip=%d, limit=%d)", user_id, skip, limit)
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d documents for user %s", len(results), user_id)
        return results

    def count_by_user(self, user_id: str) -> int:
        """
        Count total documents for a user.

        Args:
            user_id: UUID of the user.

        Returns:
            Total count of documents.
        """
        stmt = select(func.count()).select_from(Document).where(Document.user_id == user_id)
        result = self.db.execute(stmt).scalar()
        return result or 0

    def count_by_session(self, session_id: str) -> int:
        """
        Count uploaded documents in a session.

        Only counts documents with source="upload" - artifacts auto-saved
        from chat do not count against the per-session upload limit.

        Args:
            session_id: UUID of the session.

        Returns:
            Number of uploaded documents in the session.
        """
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(Document.session_id == session_id, Document.source == "upload")
        )
        result = self.db.execute(stmt).scalar()
        return result or 0

    def can_add_document(self, session_id: str) -> bool:
        """
        Check if a session can accept more uploaded documents.

        Args:
            session_id: UUID of the session.

        Returns:
            True if under the document limit, False otherwise.
        """
        count = self.count_by_session(session_id)
        return count < settings.max_documents_per_session

    def get_by_source(
        self, session_id: str, source_message_id: str, source_block_index: int
    ) -> Document | None:
        """
        Look up an artifact-sourced document by its origin message/block.

        Used as an idempotency check so the same artifact is never saved
        into the document library twice, whether saved live from a chat
        turn or re-processed by the backfill script.

        Args:
            session_id: UUID of the session.
            source_message_id: UUID of the message the artifact came from.
            source_block_index: Index of the promoted artifact within that message.

        Returns:
            The existing Document if one was already saved for this artifact, else None.
        """
        stmt = select(Document).where(
            Document.session_id == session_id,
            Document.source_message_id == source_message_id,
            Document.source_block_index == source_block_index,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def mark_indexed(self, document_id: UUID | str) -> bool:
        """
        Mark a document as indexed.

        Args:
            document_id: UUID of the document.

        Returns:
            True if updated, False if not found.
        """
        document = self.get_by_id(document_id)
        if document is None:
            return False
        document.is_indexed = True
        self.db.commit()
        logger.debug("Marked document %s as indexed", document_id)
        return True

    def delete(self, document_id: UUID | str, user_id: str | None = None) -> bool:
        """
        Delete a document by ID.

        Args:
            document_id: UUID of the document to delete.
            user_id: Optional user ID to verify ownership.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting document: %s (user_id=%s)", document_id, user_id)
        document = self.get_by_id(document_id, user_id)
        if document is None:
            logger.debug("Document not found for deletion: %s", document_id)
            return False
        self.db.delete(document)
        self.db.commit()
        logger.debug("Deleted document: %s", document_id)
        return True

    def delete_by_session(self, session_id: str, user_id: str | None = None) -> int:
        """
        Delete all documents for a session.

        Args:
            session_id: UUID of the session.
            user_id: Optional user ID to verify ownership.

        Returns:
            Number of documents deleted.
        """
        logger.debug("Deleting documents for session: %s", session_id)
        documents = self.list_by_session(session_id, user_id)
        count = 0
        for doc in documents:
            self.db.delete(doc)
            count += 1
        if count > 0:
            self.db.commit()
        logger.debug("Deleted %d documents for session %s", count, session_id)
        return count
