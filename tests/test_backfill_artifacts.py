"""Tests for scripts/backfill_artifacts.py's run_backfill()."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session as DBSession

from scripts.backfill_artifacts import run_backfill
from src.agents.knowledge import DocumentKnowledgeBase
from src.models.document import Document
from src.models.session import Message, Session as ChatSession
from src.models.transcript import Transcript
from src.models.user import User
from src.repositories.document_repository import DocumentRepository
from src.services.document_service import DocumentService

DIAGRAM_REPLY = "Here is a diagram:\n\n```mermaid\ngraph TD;\nA-->B;\n```\n"
PLAIN_REPLY = "Sure, the answer is 42."


@pytest.fixture
def chat_session(test_db: DBSession, test_user: User) -> ChatSession:
    transcript = Transcript(
        id=str(uuid4()),
        video_id="video000002",
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


def add_message(test_db: DBSession, chat_session: ChatSession, role: str, content: str) -> Message:
    message = Message(id=str(uuid4()), session_id=chat_session.id, role=role, content=content)
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


class TestRunBackfill:
    def test_creates_document_for_promoted_artifact(
        self, test_db: DBSession, chat_session: ChatSession, document_service: DocumentService
    ) -> None:
        add_message(test_db, chat_session, "assistant", DIAGRAM_REPLY)

        summary = run_backfill(test_db, dry_run=False, document_service=document_service)

        assert summary.messages_scanned == 1
        assert summary.artifacts_found == 1
        assert summary.documents_created == 1
        assert summary.documents_already_existed == 0
        assert summary.errors == []
        assert test_db.query(Document).filter(Document.source == "artifact").count() == 1

    def test_ignores_user_messages_and_plain_replies(
        self, test_db: DBSession, chat_session: ChatSession, document_service: DocumentService
    ) -> None:
        add_message(test_db, chat_session, "user", "Show me a diagram")
        add_message(test_db, chat_session, "assistant", PLAIN_REPLY)

        summary = run_backfill(test_db, dry_run=False, document_service=document_service)

        assert summary.messages_scanned == 1  # only the assistant message
        assert summary.artifacts_found == 0
        assert summary.documents_created == 0

    def test_dry_run_does_not_write(
        self, test_db: DBSession, chat_session: ChatSession, document_service: DocumentService
    ) -> None:
        add_message(test_db, chat_session, "assistant", DIAGRAM_REPLY)

        summary = run_backfill(test_db, dry_run=True, document_service=document_service)

        assert summary.documents_created == 1  # "would create" count
        assert test_db.query(Document).count() == 0

    def test_idempotent_on_repeated_runs(
        self, test_db: DBSession, chat_session: ChatSession, document_service: DocumentService
    ) -> None:
        add_message(test_db, chat_session, "assistant", DIAGRAM_REPLY)

        first = run_backfill(test_db, dry_run=False, document_service=document_service)
        second = run_backfill(test_db, dry_run=False, document_service=document_service)

        assert first.documents_created == 1
        assert second.documents_created == 0
        assert second.documents_already_existed == 1
        assert test_db.query(Document).count() == 1

    def test_safe_to_run_after_live_autosave_already_saved_the_message(
        self, test_db: DBSession, chat_session: ChatSession, document_service: DocumentService
    ) -> None:
        message = add_message(test_db, chat_session, "assistant", DIAGRAM_REPLY)

        # Simulate AgentService._save_artifacts already having saved this
        # message live, before the backfill script ever runs.
        from src.utils.artifact_parser import parse_artifacts

        artifact = parse_artifacts(message.content)[0]
        document_service.save_artifact_document(
            artifact=artifact,
            session_id=chat_session.id,
            user_id=chat_session.user_id,
            source_message_id=message.id,
            source_block_index=0,
        )

        summary = run_backfill(test_db, dry_run=False, document_service=document_service)

        assert summary.documents_created == 0
        assert summary.documents_already_existed == 1
        assert test_db.query(Document).count() == 1

    def test_multiple_sessions_and_messages(
        self, test_db: DBSession, test_user: User, document_service: DocumentService
    ) -> None:
        for i in range(3):
            transcript = Transcript(
                id=str(uuid4()),
                video_id=f"video{i:07d}z",
                title=f"Video {i}",
                transcript_text="text",
                transcript_segments=[{"text": "text", "start": 0.0, "duration": 1.0}],
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
            add_message(test_db, session, "assistant", DIAGRAM_REPLY)

        summary = run_backfill(test_db, dry_run=False, document_service=document_service)

        assert summary.messages_scanned == 3
        assert summary.documents_created == 3
