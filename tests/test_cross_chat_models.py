"""Tests for CrossChatSession, CrossChatSessionReference, and CrossChatMessage models."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session as DBSession

from src.database import Base
from src.models.cross_chat_session import (
    CrossChatMessage,
    CrossChatSession,
    CrossChatSessionReference,
)
from src.models.session import Session as ChatSession
from src.models.transcript import Transcript
from src.models.user import User


def _make_transcript(db, user_id, video_id):
    """Create and persist a Transcript record."""
    t = Transcript(
        id=str(uuid4()),
        video_id=video_id,
        user_id=user_id,
        title=f"Video {video_id}",
        channel_name="Test Channel",
        transcript_text=f"Transcript for {video_id}.",
        transcript_segments=[{"text": "hello", "start": 0.0, "duration": 1.0}],
        language="en",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_chat_session(db, user_id, transcript_id):
    """Create and persist a regular chat Session record."""
    s = ChatSession(
        id=str(uuid4()),
        transcript_id=transcript_id,
        user_id=user_id,
        model_provider="anthropic",
        model_name="claude-sonnet-4-5-20250929",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class TestCrossChatSessionCreation:
    """Tests for CrossChatSession model creation and defaults."""

    def test_create_with_all_fields(self, test_db, test_user):
        """CrossChatSession can be created with explicit values for all columns."""
        session_id = str(uuid4())
        session = CrossChatSession(
            id=session_id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)
        assert session.id == session_id
        assert session.model_provider == "anthropic"
        assert session.model_name == "claude-sonnet-4-5-20250929"
        assert session.user_id == test_user.id
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)

    def test_uuid_auto_generated(self, test_db, test_user):
        """When id is not provided, a UUID is automatically generated."""
        session = CrossChatSession(
            model_provider="openai",
            model_name="gpt-4o",
            user_id=test_user.id,
        )
        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)
        assert session.id is not None
        assert len(session.id) == 36

    def test_timestamps_auto_set(self, test_db, test_user):
        """created_at and updated_at are set automatically."""
        session = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)
        assert session.created_at is not None
        assert session.updated_at is not None


class TestCrossChatSessionReferenceCreation:
    """Tests for CrossChatSessionReference association model."""

    def test_create_reference(self, test_db, test_user):
        """CrossChatSessionReference links a cross-chat session to a chat session."""
        transcript = _make_transcript(test_db, test_user.id, "vid_ref_01")
        chat_session = _make_chat_session(test_db, test_user.id, transcript.id)
        cross_session = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(cross_session)
        test_db.commit()
        test_db.refresh(cross_session)
        ref = CrossChatSessionReference(
            cross_chat_session_id=cross_session.id,
            session_id=chat_session.id,
        )
        test_db.add(ref)
        test_db.commit()
        test_db.refresh(ref)
        assert ref.id is not None
        assert ref.cross_chat_session_id == cross_session.id
        assert ref.session_id == chat_session.id
        assert isinstance(ref.created_at, datetime)


class TestCrossChatMessageCreation:
    """Tests for CrossChatMessage model creation."""

    def test_create_user_message(self, test_db, test_user):
        """CrossChatMessage can store a user message."""
        cross_session = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(cross_session)
        test_db.commit()
        test_db.refresh(cross_session)
        msg = CrossChatMessage(
            cross_chat_session_id=cross_session.id,
            role="user",
            content="Compare the two videos.",
        )
        test_db.add(msg)
        test_db.commit()
        test_db.refresh(msg)
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Compare the two videos."

    def test_create_assistant_message_with_citations(self, test_db, test_user):
        """CrossChatMessage stores assistant message with citations."""
        cross_session = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(cross_session)
        test_db.commit()
        test_db.refresh(cross_session)
        citations = [{"text": "Python is great", "source_type": "transcript"}]
        msg = CrossChatMessage(
            cross_chat_session_id=cross_session.id,
            role="assistant",
            content="Based on the transcripts, Python is popular.",
            citations=citations,
            tokens_used=150,
        )
        test_db.add(msg)
        test_db.commit()
        test_db.refresh(msg)
        assert msg.citations is not None
        assert len(msg.citations) == 1
        assert msg.tokens_used == 150

    def test_message_defaults_nullable_fields(self, test_db, test_user):
        """citations and tokens_used default to None."""
        cross_session = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(cross_session)
        test_db.commit()
        test_db.refresh(cross_session)
        msg = CrossChatMessage(
            cross_chat_session_id=cross_session.id,
            role="user",
            content="Simple question.",
        )
        test_db.add(msg)
        test_db.commit()
        test_db.refresh(msg)
        assert msg.citations is None
        assert msg.tokens_used is None


class TestCrossChatRelationships:
    """Tests for ORM relationship navigation."""

    def _setup(self, db, user):
        t1 = _make_transcript(db, user.id, "vid_rel_01")
        t2 = _make_transcript(db, user.id, "vid_rel_02")
        s1 = _make_chat_session(db, user.id, t1.id)
        s2 = _make_chat_session(db, user.id, t2.id)
        cross = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=user.id,
        )
        db.add(cross)
        db.commit()
        db.refresh(cross)
        db.add_all([
            CrossChatSessionReference(cross_chat_session_id=cross.id, session_id=s1.id),
            CrossChatSessionReference(cross_chat_session_id=cross.id, session_id=s2.id),
        ])
        db.commit()
        db.add(CrossChatMessage(
            cross_chat_session_id=cross.id, role="user", content="Compare.",
        ))
        db.commit()
        db.refresh(cross)
        return cross, [s1, s2]

    def test_session_has_referenced_sessions(self, test_db, test_user):
        """referenced_sessions returns associated references."""
        cross, _ = self._setup(test_db, test_user)
        assert len(cross.referenced_sessions) == 2

    def test_session_has_messages(self, test_db, test_user):
        """messages returns associated messages."""
        cross, _ = self._setup(test_db, test_user)
        assert len(cross.messages) >= 1


class TestCrossChatCascadeDelete:
    """Tests for cascade delete."""

    def test_deleting_session_cascades(self, test_db, test_user):
        """Deleting CrossChatSession removes references and messages."""
        t1 = _make_transcript(test_db, test_user.id, "vid_cas_01")
        t2 = _make_transcript(test_db, test_user.id, "vid_cas_02")
        s1 = _make_chat_session(test_db, test_user.id, t1.id)
        s2 = _make_chat_session(test_db, test_user.id, t2.id)
        cross = CrossChatSession(
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            user_id=test_user.id,
        )
        test_db.add(cross)
        test_db.commit()
        test_db.refresh(cross)
        cross_id = cross.id
        test_db.add_all([
            CrossChatSessionReference(cross_chat_session_id=cross.id, session_id=s1.id),
            CrossChatSessionReference(cross_chat_session_id=cross.id, session_id=s2.id),
        ])
        test_db.commit()
        msg = CrossChatMessage(
            cross_chat_session_id=cross.id, role="user", content="Compare.",
        )
        test_db.add(msg)
        test_db.commit()
        msg_id = msg.id
        test_db.delete(cross)
        test_db.commit()
        assert test_db.get(CrossChatSession, cross_id) is None
        assert test_db.get(CrossChatMessage, msg_id) is None
        assert test_db.get(ChatSession, s1.id) is not None
        assert test_db.get(ChatSession, s2.id) is not None
