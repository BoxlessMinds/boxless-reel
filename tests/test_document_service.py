"""Tests for DocumentService.save_artifact_document and the related
DocumentRepository changes (source-based idempotency, upload-only cap)."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session as DBSession

from src.agents.knowledge import DocumentKnowledgeBase
from src.models.document import Document
from src.models.session import Message, Session as ChatSession
from src.models.transcript import Transcript
from src.models.user import User
from src.repositories.document_repository import DocumentRepository
from src.services.document_service import DocumentIndexingError, DocumentService
from src.utils.artifact_parser import ParsedArtifact


@pytest.fixture
def chat_session(test_db: DBSession, test_user: User) -> ChatSession:
    transcript = Transcript(
        id=str(uuid4()),
        video_id="video000001",
        title="Test Video",
        transcript_text="Some transcript text.",
        transcript_segments=[{"text": "Some transcript text.", "start": 0.0, "duration": 2.0}],
        language="en",
        user_id=test_user.id,
    )
    test_db.add(transcript)
    test_db.commit()

    session = ChatSession(
        id=str(uuid4()),
        transcript_id=transcript.id,
        user_id=test_user.id,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5-20250929",
    )
    test_db.add(session)
    test_db.commit()
    test_db.refresh(session)
    return session


@pytest.fixture
def assistant_message(test_db: DBSession, chat_session: ChatSession) -> Message:
    message = Message(
        id=str(uuid4()),
        session_id=chat_session.id,
        role="assistant",
        content="Here is a diagram.",
    )
    test_db.add(message)
    test_db.commit()
    test_db.refresh(message)
    return message


@pytest.fixture
def document_service(test_db: DBSession, tmp_path: Path) -> DocumentService:
    repository = DocumentRepository(test_db)
    knowledge_base = MagicMock(spec=DocumentKnowledgeBase)
    knowledge_base.index_document.return_value = 1
    return DocumentService(repository, knowledge_base=knowledge_base, storage_path=tmp_path)


@pytest.fixture
def markdown_artifact() -> ParsedArtifact:
    return ParsedArtifact(kind="markdown", title="My Report", language=None, content="# My Report\n\nBody text.")


@pytest.fixture
def diagram_artifact() -> ParsedArtifact:
    return ParsedArtifact(
        kind="mermaid", title="Flow Diagram", language=None, content="graph TD;\nA-->B;"
    )


class TestSaveArtifactDocument:
    def test_creates_document_with_artifact_source(
        self,
        document_service: DocumentService,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        diagram_artifact: ParsedArtifact,
    ) -> None:
        document = document_service.save_artifact_document(
            artifact=diagram_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=0,
        )

        assert document.source == "artifact"
        assert document.source_message_id == assistant_message.id
        assert document.source_block_index == 0
        assert document.file_type == "md"
        assert document.original_filename == "flow-diagram.md"
        assert document.is_indexed is True
        assert Path(document.file_path).exists()
        assert "graph TD" in Path(document.file_path).read_text(encoding="utf-8")

    def test_markdown_artifact_saved_verbatim(
        self,
        document_service: DocumentService,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        markdown_artifact: ParsedArtifact,
    ) -> None:
        document = document_service.save_artifact_document(
            artifact=markdown_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=0,
        )

        assert Path(document.file_path).read_text(encoding="utf-8") == markdown_artifact.content

    def test_idempotent_on_same_source(
        self,
        document_service: DocumentService,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        diagram_artifact: ParsedArtifact,
        test_db: DBSession,
    ) -> None:
        first = document_service.save_artifact_document(
            artifact=diagram_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=0,
        )
        second = document_service.save_artifact_document(
            artifact=diagram_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=0,
        )

        assert first.id == second.id
        count = (
            test_db.query(Document)
            .filter(Document.source_message_id == assistant_message.id)
            .count()
        )
        assert count == 1

    def test_different_block_index_creates_separate_document(
        self,
        document_service: DocumentService,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        diagram_artifact: ParsedArtifact,
        markdown_artifact: ParsedArtifact,
    ) -> None:
        first = document_service.save_artifact_document(
            artifact=diagram_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=0,
        )
        second = document_service.save_artifact_document(
            artifact=markdown_artifact,
            session_id=chat_session.id,
            user_id=test_user.id,
            source_message_id=assistant_message.id,
            source_block_index=1,
        )

        assert first.id != second.id

    def test_indexing_failure_raises_but_document_persists(
        self,
        test_db: DBSession,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        diagram_artifact: ParsedArtifact,
        tmp_path: Path,
    ) -> None:
        from src.agents.knowledge.exceptions import IndexingError as KBIndexingError

        repository = DocumentRepository(test_db)
        knowledge_base = MagicMock(spec=DocumentKnowledgeBase)
        knowledge_base.index_document.side_effect = KBIndexingError("boom")
        service = DocumentService(repository, knowledge_base=knowledge_base, storage_path=tmp_path)

        with pytest.raises(DocumentIndexingError):
            service.save_artifact_document(
                artifact=diagram_artifact,
                session_id=chat_session.id,
                user_id=test_user.id,
                source_message_id=assistant_message.id,
                source_block_index=0,
            )

        document = repository.get_by_source(chat_session.id, assistant_message.id, 0)
        assert document is not None
        assert document.is_indexed is False


class TestUploadCapExcludesArtifacts:
    def test_artifact_documents_do_not_count_toward_session_cap(
        self,
        document_service: DocumentService,
        chat_session: ChatSession,
        assistant_message: Message,
        test_user: User,
        test_db: DBSession,
    ) -> None:
        repository = DocumentRepository(test_db)

        for i in range(10):
            document_service.save_artifact_document(
                artifact=ParsedArtifact(
                    kind="mermaid", title=f"Diagram {i}", language=None, content=f"graph TD;\nA-->B{i};"
                ),
                session_id=chat_session.id,
                user_id=test_user.id,
                source_message_id=assistant_message.id,
                source_block_index=i,
            )

        assert repository.count_by_session(chat_session.id) == 0
        assert repository.can_add_document(chat_session.id) is True

    def test_get_by_source_returns_none_when_not_found(
        self, test_db: DBSession, chat_session: ChatSession
    ) -> None:
        repository = DocumentRepository(test_db)
        assert repository.get_by_source(chat_session.id, "nonexistent-message-id", 0) is None
