"""Document service for managing uploaded documents in chat sessions."""

import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from src.agents.knowledge import DocumentKnowledgeBase
from src.agents.knowledge.exceptions import IndexingError as KBIndexingError
from src.config import settings
from src.models.document import Document
from src.config import settings
from src.repositories.document_repository import DocumentRepository
from src.utils.artifact_parser import (
    ParsedArtifact,
    artifact_filename_for_document,
    render_artifact_as_markdown,
)
from src.utils.file_processing import (
    FILE_SIZE_LIMITS,
    ExtractionError,
    ExtractedContent,
    FileProcessor,
    FileTooLargeError as ProcessingFileTooLargeError,
    UnsupportedFileTypeError as ProcessingUnsupportedFileTypeError,
)

logger = logging.getLogger(__name__)

# Upload chunk size for streaming (1MB)
UPLOAD_CHUNK_SIZE = 1024 * 1024


class DocumentServiceError(Exception):
    """Base exception for document service errors."""

    pass


class MaxDocumentsExceededError(DocumentServiceError):
    """Raised when attempting to upload more documents than allowed per session."""

    pass


class UnsupportedFileTypeError(DocumentServiceError):
    """Raised when the file type is not supported."""

    pass


class FileTooLargeError(DocumentServiceError):
    """Raised when the file exceeds size limits."""

    pass


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document is not found."""

    pass


class DocumentIndexingError(DocumentServiceError):
    """Raised when document indexing fails."""

    pass


class DocumentService:
    """
    Service layer for document upload and management.

    Orchestrates:
    - File validation and streaming upload
    - Text extraction and chunking
    - Vector indexing in LanceDB
    - Document lifecycle management
    """

    def __init__(
        self,
        repository: DocumentRepository,
        knowledge_base: DocumentKnowledgeBase | None = None,
        storage_path: Path | None = None,
    ) -> None:
        """
        Initialize the document service.

        Args:
            repository: Repository for document database operations.
            knowledge_base: Knowledge base for vector indexing.
            storage_path: Base path for document storage.
        """
        self.repository = repository
        self.knowledge_base = knowledge_base or DocumentKnowledgeBase()
        self.storage_path = storage_path or Path(
            getattr(settings, "documents_storage_path", "./data/documents")
        )
        self.file_processor = FileProcessor()

    async def upload_document(
        self,
        file: UploadFile,
        session_id: str,
        user_id: str,
    ) -> Document:
        """
        Upload and process a document for a session.

        Handles:
        - Validation of file type and session limit
        - Streaming upload to disk
        - Text extraction
        - Chunking and vector indexing
        - Database record creation

        Args:
            file: Uploaded file from FastAPI.
            session_id: UUID of the session.
            user_id: UUID of the user.

        Returns:
            Created Document model instance.

        Raises:
            MaxDocumentsExceededError: If session has reached document limit.
            UnsupportedFileTypeError: If file type is not supported.
            FileTooLargeError: If file exceeds size limits.
            DocumentIndexingError: If text extraction or indexing fails.
        """
        # Check document limit
        if not self.repository.can_add_document(session_id):
            raise MaxDocumentsExceededError(
                f"Maximum of {settings.max_documents_per_session} documents per session reached"
            )

        # Validate file type
        original_filename = file.filename or "unknown"
        try:
            file_type = self.file_processor.validate_file_type(original_filename)
        except ProcessingUnsupportedFileTypeError as e:
            raise UnsupportedFileTypeError(str(e)) from e

        # Generate document ID and storage path
        document_id = str(uuid.uuid4())
        file_extension = Path(original_filename).suffix.lower()
        stored_filename = f"{document_id}{file_extension}"

        # Create storage directory structure: data/documents/{user_id}/{session_id}/
        storage_dir = self.storage_path / user_id / session_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / stored_filename

        # Stream file to disk with size validation
        max_size = FILE_SIZE_LIMITS.get(file_type, 5 * 1024 * 1024)
        try:
            file_size = await self._stream_to_file(file, file_path, max_size)
        except ProcessingFileTooLargeError as e:
            raise FileTooLargeError(str(e)) from e

        # Validate file content matches expected type (magic bytes)
        with open(file_path, "rb") as f:
            header_bytes = f.read(512)
        if not self.file_processor.validate_file_content(header_bytes, file_type):
            if file_path.exists():
                file_path.unlink()
            raise UnsupportedFileTypeError(
                f"File content does not match expected type: {file_type}"
            )

        # Extract text content
        try:
            content = self.file_processor.extract_text(file_path, file_type)
        except ExtractionError as e:
            # Clean up file on extraction failure
            if file_path.exists():
                file_path.unlink()
            raise DocumentIndexingError(f"Failed to extract text: {e}") from e

        # Create database record
        document = Document(
            id=document_id,
            session_id=session_id,
            user_id=user_id,
            filename=stored_filename,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            file_path=str(file_path),
            page_count=content.page_count,
            word_count=content.word_count,
            is_indexed=False,
        )
        document = self.repository.create(document)

        # Index document in knowledge base
        try:
            self._index_document(document, content)
            self.repository.mark_indexed(document_id)
            document.is_indexed = True
        except KBIndexingError as e:
            logger.error("Failed to index document %s: %s", document_id, e)
            # Document is created but not indexed - can be retried
            raise DocumentIndexingError(f"Failed to index document: {e}") from e

        logger.info(
            "Uploaded document %s (%s, %d bytes, %d words)",
            document_id,
            original_filename,
            file_size,
            content.word_count,
        )

        return document

    async def _stream_to_file(
        self,
        file: UploadFile,
        destination: Path,
        max_size: int,
    ) -> int:
        """
        Stream uploaded file to disk with size validation.

        Args:
            file: Uploaded file from FastAPI.
            destination: Target path for the file.
            max_size: Maximum allowed size in bytes.

        Returns:
            Total file size in bytes.

        Raises:
            FileTooLargeError: If file exceeds max_size.
        """
        total_size = 0

        with open(destination, "wb") as dest:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    dest.close()
                    destination.unlink()
                    max_mb = max_size / (1024 * 1024)
                    raise ProcessingFileTooLargeError(
                        f"File too large. Maximum size is {max_mb:.0f}MB"
                    )
                dest.write(chunk)

        return total_size

    def save_artifact_document(
        self,
        *,
        artifact: ParsedArtifact,
        session_id: str,
        user_id: str,
        source_message_id: str,
        source_block_index: int,
    ) -> Document:
        """
        Save a chat-generated artifact into the document library.

        Unlike upload_document(), this does not accept an UploadFile - the
        content already exists in memory (parsed from an assistant message)
        and is normalized to Markdown before being written to disk and
        indexed alongside uploaded documents. Idempotent: calling this again
        for the same (session_id, source_message_id, source_block_index)
        returns the existing document rather than creating a duplicate, so
        this is safe to call from both the live chat path and the backfill
        script.

        Does NOT count against the per-session upload limit (see
        DocumentRepository.count_by_session).

        Args:
            artifact: Parsed artifact (kind/title/language/content).
            session_id: UUID of the session the artifact was generated in.
            user_id: UUID of the session owner.
            source_message_id: UUID of the assistant message the artifact came from.
            source_block_index: Index of this artifact among promoted artifacts in that message.

        Returns:
            The created (or already-existing) Document model instance.

        Raises:
            DocumentIndexingError: If indexing fails. The document row is
                still created and can be retried later.
        """
        existing = self.repository.get_by_source(
            session_id, source_message_id, source_block_index
        )
        if existing is not None:
            return existing

        markdown_text = render_artifact_as_markdown(artifact)
        original_filename = artifact_filename_for_document(artifact)

        document_id = str(uuid.uuid4())
        stored_filename = f"{document_id}.md"

        storage_dir = self.storage_path / user_id / session_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / stored_filename
        file_path.write_text(markdown_text, encoding="utf-8")

        content = ExtractedContent.from_text(markdown_text)

        document = Document(
            id=document_id,
            session_id=session_id,
            user_id=user_id,
            filename=stored_filename,
            original_filename=original_filename,
            file_type="md",
            file_size=len(markdown_text.encode("utf-8")),
            file_path=str(file_path),
            page_count=content.page_count,
            word_count=content.word_count,
            is_indexed=False,
            source="artifact",
            source_message_id=source_message_id,
            source_block_index=source_block_index,
        )
        document = self.repository.create(document)

        try:
            self._index_document(document, content)
            self.repository.mark_indexed(document_id)
            document.is_indexed = True
        except KBIndexingError as e:
            logger.error("Failed to index artifact document %s: %s", document_id, e)
            raise DocumentIndexingError(f"Failed to index document: {e}") from e

        logger.info(
            "Saved artifact document %s (%s, message=%s, block=%d)",
            document_id,
            original_filename,
            source_message_id,
            source_block_index,
        )

        return document

    def _index_document(
        self,
        document: Document,
        content: ExtractedContent,
    ) -> int:
        """
        Index document content in the knowledge base.

        Args:
            document: Document model instance.
            content: Extracted content from the document.

        Returns:
            Number of chunks indexed.

        Raises:
            IndexingError: If indexing fails.
        """
        return self.knowledge_base.index_document(
            document_id=document.id,
            session_id=document.session_id,
            document_name=document.original_filename,
            content=content,
        )

    def get_document(
        self,
        document_id: str,
        user_id: str | None = None,
    ) -> Document:
        """
        Get a document by ID.

        Args:
            document_id: UUID of the document.
            user_id: Optional user ID for ownership verification.

        Returns:
            Document model instance.

        Raises:
            DocumentNotFoundError: If document not found.
        """
        document = self.repository.get_by_id(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        return document

    def list_session_documents(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> list[Document]:
        """
        List all documents for a session.

        Args:
            session_id: UUID of the session.
            user_id: Optional user ID for ownership verification.

        Returns:
            List of Document model instances.
        """
        return self.repository.list_by_session(session_id, user_id)

    def list_user_documents(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Document], int]:
        """
        List all documents for a user with pagination.

        Args:
            user_id: UUID of the user.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Tuple of (documents list, total count).
        """
        documents = self.repository.list_by_user(user_id, skip, limit)
        total = self.repository.count_by_user(user_id)
        return documents, total

    def delete_document(
        self,
        document_id: str,
        user_id: str | None = None,
    ) -> bool:
        """
        Delete a document and its associated data.

        Removes:
        - Document file from storage
        - Chunks from vector knowledge base
        - Database record

        Args:
            document_id: UUID of the document.
            user_id: Optional user ID for ownership verification.

        Returns:
            True if deleted successfully.

        Raises:
            DocumentNotFoundError: If document not found.
        """
        document = self.repository.get_by_id(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found")

        # Delete from knowledge base
        self.knowledge_base.delete_document(document_id)

        # Delete file from storage
        file_path = Path(document.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
                logger.debug("Deleted file: %s", file_path)
            except OSError as e:
                logger.warning("Failed to delete file %s: %s", file_path, e)

        # Delete database record
        deleted = self.repository.delete(document_id, user_id)

        if deleted:
            logger.info("Deleted document %s", document_id)

        return deleted

    def delete_session_documents(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> int:
        """
        Delete all documents for a session.

        Args:
            session_id: UUID of the session.
            user_id: Optional user ID for ownership verification.

        Returns:
            Number of documents deleted.
        """
        documents = self.repository.list_by_session(session_id, user_id)
        deleted_count = 0

        for document in documents:
            try:
                self.delete_document(document.id, user_id)
                deleted_count += 1
            except DocumentNotFoundError:
                continue

        # Also clean up knowledge base session data
        self.knowledge_base.delete_session_documents(session_id)

        logger.info("Deleted %d documents for session %s", deleted_count, session_id)
        return deleted_count

    def get_session_document_count(self, session_id: str) -> int:
        """
        Get the number of documents in a session.

        Args:
            session_id: UUID of the session.

        Returns:
            Document count.
        """
        return self.repository.count_by_session(session_id)

    def can_add_document(self, session_id: str) -> bool:
        """
        Check if a session can accept more documents.

        Args:
            session_id: UUID of the session.

        Returns:
            True if under the document limit.
        """
        return self.repository.can_add_document(session_id)
