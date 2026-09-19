"""Repository for session and message database operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession, joinedload

from src.models.session import Message, Session

logger = logging.getLogger(__name__)


class SessionRepository:
    """Data access layer for session and message operations."""

    def __init__(self, db: DBSession) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(
        self,
        session_id: str,
        transcript_id: str,
        user_id: str,
        model_provider: str,
        model_name: str,
    ) -> Session:
        """
        Create a new session record.

        Args:
            session_id: Unique session identifier.
            transcript_id: UUID of the associated transcript.
            user_id: UUID of the session owner.
            model_provider: LLM provider name.
            model_name: Specific model identifier.

        Returns:
            The persisted session.
        """
        logger.debug(
            "Creating session %s for transcript %s (user=%s)", session_id, transcript_id, user_id
        )
        session = Session(
            id=session_id,
            transcript_id=transcript_id,
            user_id=user_id,
            model_provider=model_provider,
            model_name=model_name,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        logger.debug("Created session: %s", session_id)
        return session

    def get(self, session_id: str, user_id: str | None = None) -> Session | None:
        """
        Get a session by ID with its messages.

        Args:
            session_id: The session identifier.
            user_id: Optional user ID to verify ownership.

        Returns:
            Session with messages if found, None otherwise.
        """
        logger.debug("Fetching session: %s (user_id=%s)", session_id, user_id)
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .options(joinedload(Session.messages))
        )
        if user_id:
            stmt = stmt.where(Session.user_id == user_id)
        result = self.db.execute(stmt).unique().scalar_one_or_none()
        if result is None:
            logger.debug("Session not found: %s", session_id)
        return result

    def get_with_transcript(self, session_id: str, user_id: str | None = None) -> Session | None:
        """
        Get a session by ID with its transcript and messages.

        Args:
            session_id: The session identifier.
            user_id: Optional user ID to verify ownership.

        Returns:
            Session with transcript and messages if found, None otherwise.
        """
        logger.debug("Fetching session with transcript: %s (user_id=%s)", session_id, user_id)
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .options(joinedload(Session.messages), joinedload(Session.transcript))
        )
        if user_id:
            stmt = stmt.where(Session.user_id == user_id)
        result = self.db.execute(stmt).unique().scalar_one_or_none()
        if result is None:
            logger.debug("Session not found: %s", session_id)
        return result

    def list(self, user_id: str, transcript_id: str | None = None) -> list[Session]:
        """
        List sessions for a user, optionally filtered by transcript ID.

        Args:
            user_id: User ID to filter sessions by ownership.
            transcript_id: Optional filter by transcript ID.

        Returns:
            List of sessions.
        """
        logger.debug("Listing sessions (user_id=%s, transcript_id=%s)", user_id, transcript_id)
        stmt = (
            select(Session)
            .where(Session.user_id == user_id)
            .options(joinedload(Session.messages))
        )

        if transcript_id:
            stmt = stmt.where(Session.transcript_id == transcript_id)

        stmt = stmt.order_by(Session.updated_at.desc())
        results = list(self.db.execute(stmt).unique().scalars().all())
        logger.debug("Found %d sessions", len(results))
        return results

    def delete(self, session_id: str, user_id: str | None = None) -> bool:
        """
        Delete a session and all its messages.

        Args:
            session_id: The session identifier.
            user_id: Optional user ID to verify ownership.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting session: %s (user_id=%s)", session_id, user_id)
        stmt = select(Session).where(Session.id == session_id)
        if user_id:
            stmt = stmt.where(Session.user_id == user_id)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session is None:
            logger.debug("Session not found for deletion: %s", session_id)
            return False
        self.db.delete(session)
        self.db.commit()
        logger.debug("Deleted session: %s", session_id)
        return True

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        tokens_used: int | None = None,
    ) -> Message:
        """
        Add a message to a session.

        Args:
            session_id: The session identifier.
            role: Message role ("user" or "assistant").
            content: Message content.
            citations: Optional list of citation dictionaries.
            tokens_used: Optional token count.

        Returns:
            The persisted message.
        """
        logger.debug("Adding %s message to session %s", role, session_id)
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            citations=citations,
            tokens_used=tokens_used,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        # Update session's updated_at timestamp
        stmt = select(Session).where(Session.id == session_id)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session:
            session.updated_at = datetime.now(timezone.utc)
            self.db.commit()

        logger.debug("Added message to session %s", session_id)
        return message

    def get_messages(self, session_id: str) -> list[Message]:
        """
        Get all messages for a session in chronological order.

        Args:
            session_id: The session identifier.

        Returns:
            List of messages ordered by creation time.
        """
        logger.debug("Fetching messages for session: %s", session_id)
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d messages", len(results))
        return results

    def update_activity(self, session_id: str) -> None:
        """
        Update a session's last activity timestamp.

        Args:
            session_id: The session identifier.
        """
        logger.debug("Updating activity for session: %s", session_id)
        stmt = select(Session).where(Session.id == session_id)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session:
            # Touch the session to trigger onupdate
            self.db.add(session)
            self.db.commit()
            logger.debug("Updated activity for session: %s", session_id)
