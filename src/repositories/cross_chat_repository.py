"""Repository for cross-chat session database operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession, joinedload

from src.models.cross_chat_session import (
    CrossChatMessage,
    CrossChatSession,
    CrossChatSessionReference,
)
from src.models.session import Session

logger = logging.getLogger(__name__)


class CrossChatRepository:
    """Data access layer for cross-chat session operations."""

    def __init__(self, db: DBSession) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def create(
        self,
        user_id: str,
        session_ids: list[str],
        model_provider: str,
        model_name: str,
    ) -> CrossChatSession:
        """
        Create a new cross-chat session with references to agent sessions.

        Args:
            user_id: UUID of the session owner.
            session_ids: List of agent session IDs to reference.
            model_provider: LLM provider name.
            model_name: Specific model identifier.

        Returns:
            The persisted cross-chat session with references loaded.
        """
        logger.debug(
            "Creating cross-chat session for user %s with %d sessions",
            user_id,
            len(session_ids),
        )
        cross_chat = CrossChatSession(
            user_id=user_id,
            model_provider=model_provider,
            model_name=model_name,
        )
        self.db.add(cross_chat)
        self.db.flush()

        for sid in session_ids:
            ref = CrossChatSessionReference(
                cross_chat_session_id=cross_chat.id,
                session_id=sid,
            )
            self.db.add(ref)

        self.db.commit()
        self.db.refresh(cross_chat)

        return self.get_by_id(cross_chat.id, user_id)

    def get_by_id(self, cross_chat_id: str, user_id: str) -> CrossChatSession | None:
        """
        Get a cross-chat session by ID with referenced sessions loaded.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user to verify ownership.

        Returns:
            CrossChatSession with references if found, None otherwise.
        """
        logger.debug("Fetching cross-chat session: %s (user=%s)", cross_chat_id, user_id)
        stmt = (
            select(CrossChatSession)
            .where(CrossChatSession.id == cross_chat_id, CrossChatSession.user_id == user_id)
            .options(
                joinedload(CrossChatSession.referenced_sessions)
                .joinedload(CrossChatSessionReference.session)
                .joinedload(Session.transcript),
                joinedload(CrossChatSession.messages),
            )
        )
        result = self.db.execute(stmt).unique().scalar_one_or_none()
        if result is None:
            logger.debug("Cross-chat session not found: %s", cross_chat_id)
        return result

    def list_all(self, user_id: str) -> list[CrossChatSession]:
        """
        List all cross-chat sessions for a user.

        Args:
            user_id: UUID of the user.

        Returns:
            List of cross-chat sessions ordered by last update.
        """
        logger.debug("Listing cross-chat sessions for user %s", user_id)
        stmt = (
            select(CrossChatSession)
            .where(CrossChatSession.user_id == user_id)
            .options(
                joinedload(CrossChatSession.referenced_sessions)
                .joinedload(CrossChatSessionReference.session)
                .joinedload(Session.transcript),
                joinedload(CrossChatSession.messages),
            )
            .order_by(CrossChatSession.updated_at.desc())
        )
        results = list(self.db.execute(stmt).unique().scalars().all())
        logger.debug("Found %d cross-chat sessions", len(results))
        return results

    def delete(self, cross_chat_id: str, user_id: str) -> bool:
        """
        Delete a cross-chat session and all its references and messages.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user to verify ownership.

        Returns:
            True if deleted, False if not found.
        """
        logger.debug("Deleting cross-chat session: %s (user=%s)", cross_chat_id, user_id)
        stmt = select(CrossChatSession).where(
            CrossChatSession.id == cross_chat_id, CrossChatSession.user_id == user_id
        )
        session = self.db.execute(stmt).scalar_one_or_none()
        if session is None:
            logger.debug("Cross-chat session not found for deletion: %s", cross_chat_id)
            return False
        self.db.delete(session)
        self.db.commit()
        logger.debug("Deleted cross-chat session: %s", cross_chat_id)
        return True

    def add_message(
        self,
        cross_chat_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        tokens_used: int | None = None,
    ) -> CrossChatMessage:
        """
        Add a message to a cross-chat session.

        Args:
            cross_chat_id: The cross-chat session identifier.
            role: Message role (user or assistant).
            content: Message content.
            citations: Optional list of citation dictionaries.
            tokens_used: Optional token count.

        Returns:
            The persisted message.
        """
        logger.debug("Adding %s message to cross-chat session %s", role, cross_chat_id)
        message = CrossChatMessage(
            cross_chat_session_id=cross_chat_id,
            role=role,
            content=content,
            citations=citations,
            tokens_used=tokens_used,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        stmt = select(CrossChatSession).where(CrossChatSession.id == cross_chat_id)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session:
            session.updated_at = datetime.now(timezone.utc)
            self.db.commit()

        logger.debug("Added message to cross-chat session %s", cross_chat_id)
        return message
