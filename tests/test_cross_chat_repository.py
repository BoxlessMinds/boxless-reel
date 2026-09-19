"""Tests for CrossChatRepository database operations."""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session as DBSession

from src.models.cross_chat_session import (
    CrossChatMessage,
    CrossChatSession,
    CrossChatSessionReference,
)
from src.models.session import Session as ChatSession
from src.models.transcript import Transcript
from src.models.user import User
from src.repositories.cross_chat_repository import CrossChatRepository


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


def _make_two_sessions(db, user):
    """Create 2 chat sessions with transcripts for a user."""
    t1 = _make_transcript(db, user.id, f"vid_{uuid4().hex[:6]}")
    t2 = _make_transcript(db, user.id, f"vid_{uuid4().hex[:6]}")
    s1 = _make_chat_session(db, user.id, t1.id)
    s2 = _make_chat_session(db, user.id, t2.id)
    return [s1, s2]


class TestCrossChatRepositoryCreate:
    """Tests for CrossChatRepository.create()."""

    def test_create_session_with_references(self, test_db, test_user):
        """create() persists a CrossChatSession with session references."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)

        result = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        assert result is not None
        assert result.id is not None
        assert result.model_provider == "anthropic"
        assert result.model_name == "claude-sonnet-4-5-20250929"
        assert result.user_id == test_user.id
        assert len(result.referenced_sessions) == 2


class TestCrossChatRepositoryGetById:
    """Tests for CrossChatRepository.get_by_id()."""

    def test_get_by_id_returns_session(self, test_db, test_user):
        """get_by_id() returns the cross-chat session when it exists."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        result = repo.get_by_id(created.id, user_id=test_user.id)

        assert result is not None
        assert result.id == created.id

    def test_get_by_id_returns_none_for_missing(self, test_db, test_user):
        """get_by_id() returns None when session does not exist."""
        repo = CrossChatRepository(test_db)

        result = repo.get_by_id(str(uuid4()), user_id=test_user.id)

        assert result is None

    def test_get_by_id_with_user_id_filter(self, test_db, test_user, test_admin):
        """get_by_id() with user_id only returns sessions owned by that user."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        # Owner can access
        assert repo.get_by_id(created.id, test_user.id) is not None
        # Other user cannot access
        assert repo.get_by_id(created.id, test_admin.id) is None


class TestCrossChatRepositoryGetByIdWithDetails:
    """Tests for CrossChatRepository.get_by_id() loading full details."""

    def test_get_by_id_loads_relationships(self, test_db, test_user):
        """get_by_id() eagerly loads references and messages."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )
        # Add a message
        repo.add_message(
            cross_chat_id=created.id,
            role="user",
            content="Test question",
        )

        result = repo.get_by_id(created.id, user_id=test_user.id)

        assert result is not None
        assert len(result.referenced_sessions) == 2
        assert len(result.messages) == 1
        assert result.messages[0].content == "Test question"


class TestCrossChatRepositoryListAll:
    """Tests for CrossChatRepository.list_all()."""

    def test_list_all_returns_user_sessions(self, test_db, test_user):
        """list_all() returns all cross-chat sessions for a user."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )
        repo.create(
            user_id=test_user.id,
            model_provider="openai",
            model_name="gpt-4o",
            session_ids=[s.id for s in sessions],
        )

        result = repo.list_all(user_id=test_user.id)

        assert len(result) == 2

    def test_list_all_returns_empty_for_other_user(self, test_db, test_user, test_admin):
        """list_all() returns empty list when user has no sessions."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        result = repo.list_all(user_id=test_admin.id)

        assert len(result) == 0


class TestCrossChatRepositoryDelete:
    """Tests for CrossChatRepository.delete()."""

    def test_delete_removes_session(self, test_db, test_user):
        """delete() removes the cross-chat session and returns True."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        result = repo.delete(created.id, user_id=test_user.id)

        assert result is True
        assert repo.get_by_id(created.id, user_id=test_user.id) is None

    def test_delete_returns_false_for_missing(self, test_db, test_user):
        """delete() returns False when session does not exist."""
        repo = CrossChatRepository(test_db)

        result = repo.delete(str(uuid4()), user_id=test_user.id)

        assert result is False

    def test_delete_cascades_to_children(self, test_db, test_user):
        """delete() cascades to references and messages."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )
        repo.add_message(
            cross_chat_id=created.id,
            role="user",
            content="Test",
        )
        created_id = created.id

        repo.delete(created_id, user_id=test_user.id)

        # References and messages should be gone
        assert test_db.get(CrossChatSession, created_id) is None


class TestCrossChatRepositoryAddMessage:
    """Tests for CrossChatRepository.add_message()."""

    def test_add_message_creates_message(self, test_db, test_user):
        """add_message() persists a message for the cross-chat session."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        msg = repo.add_message(
            cross_chat_id=created.id,
            role="user",
            content="What do these videos have in common?",
        )

        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "What do these videos have in common?"
        assert msg.cross_chat_session_id == created.id

    def test_add_message_with_citations_and_tokens(self, test_db, test_user):
        """add_message() stores citations and token count."""
        sessions = _make_two_sessions(test_db, test_user)
        repo = CrossChatRepository(test_db)
        created = repo.create(
            user_id=test_user.id,
            model_provider="anthropic",
            model_name="claude-sonnet-4-5-20250929",
            session_ids=[s.id for s in sessions],
        )

        citations = [{"text": "shared topic", "source_type": "transcript"}]
        msg = repo.add_message(
            cross_chat_id=created.id,
            role="assistant",
            content="Both videos discuss Python.",
            citations=citations,
            tokens_used=200,
        )

        assert msg.citations is not None
        assert len(msg.citations) == 1
        assert msg.tokens_used == 200
