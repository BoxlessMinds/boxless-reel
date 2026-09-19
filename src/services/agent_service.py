"""Agent service for transcript querying with LLM-powered agents."""

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agents import (
    AgentConfig,
    AgentNotConfiguredError,
    AgentResponse,
    QueryError,
    TranscriptNotIndexedError,
    TranscriptQueryAgent,
    get_agent_config,
)
from src.agents.knowledge import (
    DocumentKnowledgeBase,
    IndexingError as KBIndexingError,
    TranscriptKnowledgeBase,
)
from src.repositories import SessionRepository, TranscriptRepository
from src.services.document_service import DocumentService
from src.services.exceptions import (
    AgentNotAvailableError,
    IndexingError,
    QueryExecutionError,
    SessionNotFoundError,
    TranscriptNotFoundError,
)
from src.models.session import Session as SessionModel, Message as MessageModel
from src.utils.artifact_parser import parse_artifacts

logger = logging.getLogger(__name__)

# Maximum number of sessions to keep in memory before evicting oldest
_MAX_REGISTRY_SIZE = 500


class _BoundedDict(OrderedDict):
    """OrderedDict with a maximum size — evicts oldest entries when full."""

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > _MAX_REGISTRY_SIZE:
            self.popitem(last=False)


# Module-level registries to persist sessions across service instances
# (FastAPI creates a new service instance per request)
_sessions_registry: _BoundedDict = _BoundedDict()
_agents_registry: _BoundedDict = _BoundedDict()


@dataclass
class SessionInfo:
    """
    Information about an active agent session.

    Attributes:
        session_id: Unique session identifier.
        transcript_id: UUID of the transcript being queried.
        video_id: YouTube video ID.
        video_title: Title of the video.
        thumbnail_url: Video thumbnail URL.
        model_provider: LLM provider used ("anthropic" or "openai").
        model_id: Specific model ID being used.
        created_at: When the session was created.
        last_activity: When the session was last used.
        query_count: Number of queries made in this session.
    """

    session_id: str
    transcript_id: str
    video_id: str
    video_title: str
    thumbnail_url: str | None
    model_provider: str
    model_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    query_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "session_id": self.session_id,
            "transcript_id": self.transcript_id,
            "video_id": self.video_id,
            "video_title": self.video_title,
            "thumbnail_url": self.thumbnail_url,
            "model_provider": self.model_provider,
            "model_id": self.model_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "query_count": self.query_count,
        }


@dataclass
class QueryResponse:
    """
    Response from an agent query.

    Attributes:
        content: The agent's response text.
        citations: List of citation dictionaries with timestamps/URLs.
        session_id: Session identifier for follow-up queries.
        model_used: Model that generated the response.
        transcript_results_used: Number of transcript chunks used.
        web_results_used: Number of web search results used.
        created_at: When the response was generated.
    """

    content: str
    citations: list[dict[str, Any]]
    session_id: str
    model_used: str
    transcript_results_used: int
    web_results_used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "content": self.content,
            "citations": self.citations,
            "session_id": self.session_id,
            "model_used": self.model_used,
            "transcript_results_used": self.transcript_results_used,
            "web_results_used": self.web_results_used,
            "created_at": self.created_at.isoformat(),
        }


class AgentService:
    """
    Service layer for agent-powered transcript querying.

    Orchestrates:
    - Session lifecycle management
    - Transcript indexing coordination
    - Query execution via TranscriptQueryAgent

    Usage:
        service = AgentService(repository)
        session = service.create_session(transcript_id, model_provider="anthropic")
        response = service.query(session.session_id, "What is discussed?")
    """

    def __init__(
        self,
        repository: TranscriptRepository,
        session_repository: SessionRepository | None = None,
        config: AgentConfig | None = None,
        document_service: DocumentService | None = None,
    ) -> None:
        """
        Initialize the agent service.

        Args:
            repository: Repository for transcript database operations.
            session_repository: Repository for session/message database operations.
            config: Agent configuration. Uses get_agent_config() if None.
            document_service: Service used to auto-save chat-generated
                artifacts into the document library. Artifact auto-save is
                skipped entirely if not provided.
        """
        self.repository = repository
        self.session_repository = session_repository
        self.config = config or get_agent_config()
        self.document_service = document_service

        # Use module-level registries (shared across service instances)
        self._sessions = _sessions_registry
        self._agents = _agents_registry

        # Shared knowledge base instances (lazy-loaded)
        self._knowledge_base: TranscriptKnowledgeBase | None = None
        self._document_knowledge_base: DocumentKnowledgeBase | None = None

    @property
    def knowledge_base(self) -> TranscriptKnowledgeBase:
        """
        Get or create the shared transcript knowledge base instance.

        Returns:
            TranscriptKnowledgeBase instance.
        """
        if self._knowledge_base is None:
            self._knowledge_base = TranscriptKnowledgeBase(config=self.config)
        return self._knowledge_base

    @property
    def document_knowledge_base(self) -> DocumentKnowledgeBase:
        """
        Get or create the shared document knowledge base instance.

        Returns:
            DocumentKnowledgeBase instance.
        """
        if self._document_knowledge_base is None:
            self._document_knowledge_base = DocumentKnowledgeBase(config=self.config)
        return self._document_knowledge_base

    @property
    def is_available(self) -> bool:
        """
        Check if agent features are available.

        Returns:
            True if at least one LLM provider is configured.
        """
        return self.config.is_enabled

    def _ensure_available(self) -> None:
        """
        Ensure agent features are available.

        Raises:
            AgentNotAvailableError: If no LLM providers configured.
        """
        if not self.is_available:
            raise AgentNotAvailableError(
                "Agent features require an LLM API key. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

    def _get_transcript_or_raise(self, transcript_id: str, user_id: str):
        """
        Get transcript from repository or raise error.

        Args:
            transcript_id: UUID of the transcript.
            user_id: UUID of the user who owns the transcript.

        Returns:
            Transcript model instance.

        Raises:
            TranscriptNotFoundError: If transcript not found or not owned by user.
        """
        transcript = self.repository.get_by_id(transcript_id, user_id=user_id)
        if transcript is None:
            raise TranscriptNotFoundError(f"Transcript {transcript_id} not found")
        return transcript

    def index_transcript(self, transcript_id: str, user_id: str) -> int:
        """
        Index a transcript for agent querying.

        Loads the transcript into the vector knowledge base for
        semantic search. Safe to call multiple times (re-indexes).

        Args:
            transcript_id: UUID of the transcript to index.
            user_id: UUID of the user who owns the transcript.

        Returns:
            Number of chunks indexed.

        Raises:
            AgentNotAvailableError: If no LLM providers configured.
            TranscriptNotFoundError: If transcript not found or not owned by user.
            IndexingError: If indexing fails.
        """
        self._ensure_available()

        transcript = self._get_transcript_or_raise(transcript_id, user_id)

        logger.info("Indexing transcript %s", transcript_id)

        try:
            chunk_count = self.knowledge_base.load_transcript(
                transcript_id=str(transcript.id),
                transcript_text=transcript.transcript_text,
                transcript_segments=transcript.transcript_segments,
                video_id=transcript.video_id,
            )

            logger.info(
                "Indexed %d chunks for transcript %s",
                chunk_count,
                transcript_id,
            )

            return chunk_count

        except KBIndexingError as e:
            logger.error("Failed to index transcript %s: %s", transcript_id, e)
            raise IndexingError(f"Failed to index transcript: {e}") from e

    def is_indexed(self, transcript_id: str) -> bool:
        """
        Check if a transcript is indexed.

        Args:
            transcript_id: UUID of the transcript.

        Returns:
            True if transcript has been indexed.
        """
        return self.knowledge_base.is_indexed(transcript_id)

    def create_session(
        self,
        transcript_id: str,
        user_id: str,
        model_provider: str | None = None,
    ) -> SessionInfo:
        """
        Create a new agent session for a transcript.

        Automatically indexes the transcript if not already indexed.

        Args:
            transcript_id: UUID of the transcript to query.
            user_id: UUID of the user creating the session.
            model_provider: LLM provider ("anthropic" or "openai").
                          Uses default if not specified.

        Returns:
            SessionInfo with session details.

        Raises:
            AgentNotAvailableError: If no LLM providers configured.
            TranscriptNotFoundError: If transcript not found or not owned by user.
            IndexingError: If auto-indexing fails.
        """
        self._ensure_available()

        transcript = self._get_transcript_or_raise(transcript_id, user_id)

        # Auto-index if needed
        if not self.is_indexed(str(transcript.id)):
            logger.info("Auto-indexing transcript %s for new session", transcript_id)
            self.index_transcript(str(transcript.id), user_id)

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Validate provider
        validated_provider = self.config.validate_provider(model_provider)
        model_id = self.config.get_model_id(validated_provider)

        # Create session info
        session_info = SessionInfo(
            session_id=session_id,
            transcript_id=str(transcript.id),
            video_id=transcript.video_id,
            video_title=transcript.title,
            thumbnail_url=transcript.thumbnail_url,
            model_provider=validated_provider,
            model_id=model_id,
        )

        # Create agent instance with document knowledge base
        try:
            agent = TranscriptQueryAgent(
                transcript_id=str(transcript.id),
                video_title=transcript.title,
                video_id=transcript.video_id,
                channel_name=transcript.channel_name,
                duration_seconds=transcript.duration_seconds,
                session_id=session_id,
                model_provider=validated_provider,
                config=self.config,
                document_knowledge_base=self.document_knowledge_base,
            )
        except AgentNotConfiguredError as e:
            raise AgentNotAvailableError(str(e)) from e
        except TranscriptNotIndexedError as e:
            # This shouldn't happen since we auto-index, but handle it
            raise IndexingError(str(e)) from e

        # Store session and agent in memory
        self._sessions[session_id] = session_info
        self._agents[session_id] = agent

        # Persist session to database
        if self.session_repository:
            self.session_repository.create(
                session_id=session_id,
                transcript_id=str(transcript.id),
                user_id=user_id,
                model_provider=validated_provider,
                model_name=model_id,
            )

        logger.info(
            "Created session %s for transcript %s with provider %s (documents enabled)",
            session_id,
            transcript_id,
            validated_provider,
        )

        return session_info

    def get_session(self, session_id: str, user_id: str) -> SessionInfo:
        """
        Get session information.

        Tries memory first (with ownership validation), then database.
        If found in database but not in memory, restores the session and agent.

        Args:
            session_id: The session identifier.
            user_id: UUID of the user who owns the session.

        Returns:
            SessionInfo for the session.

        Raises:
            SessionNotFoundError: If session not found or not owned by user.
        """
        # Try memory first
        if session_id in self._sessions:
            # Validate ownership via database if repository available
            if self.session_repository:
                db_session = self.session_repository.get(session_id, user_id=user_id)
                if db_session is None:
                    raise SessionNotFoundError(f"Session {session_id} not found")
            return self._sessions[session_id]

        # Try database if repository available
        if self.session_repository:
            db_session = self.session_repository.get_with_transcript(session_id, user_id=user_id)
            if db_session:
                # Restore session from database
                return self._restore_session(db_session)

        raise SessionNotFoundError(f"Session {session_id} not found")

    def query(self, session_id: str, user_id: str, question: str) -> QueryResponse:
        """
        Execute a query against a transcript.

        Args:
            session_id: The session identifier.
            user_id: UUID of the user who owns the session.
            question: The question to ask about the transcript.

        Returns:
            QueryResponse with answer and citations.

        Raises:
            SessionNotFoundError: If session not found or not owned by user.
            QueryExecutionError: If query fails.
        """
        # Get session (restores from DB if needed)
        session = self.get_session(session_id, user_id)

        if session_id not in self._agents:
            raise SessionNotFoundError(f"Agent for session {session_id} not found")

        agent = self._agents[session_id]

        logger.debug(
            "Processing query for session %s: %s",
            session_id,
            question[:100],
        )

        # Save user message to database before query
        if self.session_repository:
            self.session_repository.add_message(
                session_id=session_id,
                role="user",
                content=question,
            )

        try:
            response: AgentResponse = agent.query(question)

            # Update session metadata
            session.last_activity = datetime.now(timezone.utc)
            session.query_count += 1

            # Save assistant response to database
            if self.session_repository:
                citations = [c.to_dict() for c in response.citations]
                assistant_message = self.session_repository.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=response.content,
                    citations=citations,
                )
                self._save_artifacts(assistant_message, session_id, user_id)

            return QueryResponse(
                content=response.content,
                citations=[c.to_dict() for c in response.citations],
                session_id=session_id,
                model_used=response.model_used,
                transcript_results_used=response.transcript_results_used,
                web_results_used=response.web_results_used,
                created_at=response.created_at,
            )

        except QueryError as e:
            logger.error("Query failed for session %s: %s", session_id, e)
            raise QueryExecutionError(f"Query failed: {e}") from e

    def _save_artifacts(
        self, message: MessageModel, session_id: str, user_id: str
    ) -> None:
        """
        Auto-save promoted artifacts from an assistant message into the
        document library.

        Best-effort: any failure (parsing, storage, indexing) is logged and
        swallowed rather than raised, since an artifact-save problem must
        never fail the user's chat turn.
        """
        if not self.document_service:
            return

        try:
            artifacts = parse_artifacts(message.content)
            for block_index, artifact in enumerate(artifacts):
                self.document_service.save_artifact_document(
                    artifact=artifact,
                    session_id=session_id,
                    user_id=user_id,
                    source_message_id=message.id,
                    source_block_index=block_index,
                )
        except Exception:
            logger.exception(
                "Failed to auto-save artifacts for message %s in session %s",
                message.id,
                session_id,
            )

    def query_oneshot(
        self,
        transcript_id: str,
        user_id: str,
        question: str,
        model_provider: str | None = None,
    ) -> QueryResponse:
        """
        Execute a one-shot query without creating a persistent session.

        Useful for single questions where conversation history is not needed.
        Automatically indexes the transcript if not already indexed.

        Args:
            transcript_id: UUID of the transcript to query.
            user_id: UUID of the user who owns the transcript.
            question: The question to ask.
            model_provider: LLM provider to use.

        Returns:
            QueryResponse with answer and citations.

        Raises:
            AgentNotAvailableError: If no LLM providers configured.
            TranscriptNotFoundError: If transcript not found or not owned by user.
            IndexingError: If indexing fails.
            QueryExecutionError: If query fails.
        """
        self._ensure_available()

        transcript = self._get_transcript_or_raise(transcript_id, user_id)

        # Auto-index if needed
        if not self.is_indexed(str(transcript.id)):
            logger.info("Auto-indexing transcript %s for one-shot query", transcript_id)
            self.index_transcript(str(transcript.id), user_id)

        # Validate provider
        validated_provider = self.config.validate_provider(model_provider)

        # Create temporary agent (no session_id for stateless query, no documents)
        try:
            agent = TranscriptQueryAgent(
                transcript_id=str(transcript.id),
                video_title=transcript.title,
                video_id=transcript.video_id,
                channel_name=transcript.channel_name,
                duration_seconds=transcript.duration_seconds,
                session_id=None,  # No session for one-shot
                model_provider=validated_provider,
                config=self.config,
                document_knowledge_base=None,  # No documents for one-shot queries
            )
        except AgentNotConfiguredError as e:
            raise AgentNotAvailableError(str(e)) from e
        except TranscriptNotIndexedError as e:
            raise IndexingError(str(e)) from e

        logger.debug(
            "Processing one-shot query for transcript %s: %s",
            transcript_id,
            question[:100],
        )

        try:
            response: AgentResponse = agent.query(question)

            return QueryResponse(
                content=response.content,
                citations=[c.to_dict() for c in response.citations],
                session_id="",  # No session for one-shot
                model_used=response.model_used,
                transcript_results_used=response.transcript_results_used,
                web_results_used=response.web_results_used,
                created_at=response.created_at,
            )

        except QueryError as e:
            logger.error(
                "One-shot query failed for transcript %s: %s",
                transcript_id,
                e,
            )
            raise QueryExecutionError(f"Query failed: {e}") from e

    def delete_session(self, session_id: str, user_id: str) -> None:
        """
        Delete an agent session.

        Removes the session from both memory and database.

        Args:
            session_id: The session identifier.
            user_id: UUID of the user who owns the session.

        Raises:
            SessionNotFoundError: If session not found or not owned by user.
        """
        # Check if exists in memory or database (with ownership verification)
        in_memory = session_id in self._sessions
        in_database = False

        if self.session_repository:
            db_session = self.session_repository.get(session_id, user_id=user_id)
            in_database = db_session is not None

        if not in_memory and not in_database:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Verify ownership if in memory but need to check database
        if in_memory and self.session_repository:
            db_session = self.session_repository.get(session_id, user_id=user_id)
            if db_session is None:
                raise SessionNotFoundError(f"Session {session_id} not found")

        # Remove from memory registries
        if in_memory:
            del self._sessions[session_id]
            if session_id in self._agents:
                del self._agents[session_id]

        # Remove from database
        if self.session_repository and in_database:
            self.session_repository.delete(session_id, user_id=user_id)

        logger.info("Deleted session %s (user=%s)", session_id, user_id)

    def list_sessions(
        self,
        user_id: str,
        transcript_id: str | None = None,
    ) -> list[SessionInfo]:
        """
        List all sessions for a user from database.

        Args:
            user_id: UUID of the user who owns the sessions.
            transcript_id: Optional filter by transcript ID.

        Returns:
            List of SessionInfo objects owned by the user.
        """
        # Get from database if repository available
        if self.session_repository:
            db_sessions = self.session_repository.list(user_id=user_id, transcript_id=transcript_id)
            return [self._db_session_to_session_info(s) for s in db_sessions]

        # Fallback to memory-only (not user-scoped, but database should be used)
        sessions = list(self._sessions.values())
        if transcript_id:
            sessions = [s for s in sessions if s.transcript_id == transcript_id]
        return sessions

    def get_session_history(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        """
        Get conversation history for a session.

        Tries database first (authoritative source), falls back to agent memory.

        Args:
            session_id: The session identifier.
            user_id: UUID of the user who owns the session.

        Returns:
            List of message dictionaries with role, content, and citations.

        Raises:
            SessionNotFoundError: If session not found or not owned by user.
        """
        # Get from database if repository available
        if self.session_repository:
            # First verify ownership
            db_session = self.session_repository.get(session_id, user_id=user_id)
            if db_session:
                messages = self.session_repository.get_messages(session_id)
                if messages:
                    return [
                        {
                            "role": msg.role,
                            "content": msg.content,
                            "citations": msg.citations,
                            "timestamp": msg.created_at.isoformat(),
                        }
                        for msg in messages
                    ]
                return []

        # Fallback to agent memory (with ownership check via database)
        if session_id in self._agents:
            if self.session_repository:
                db_session = self.session_repository.get(session_id, user_id=user_id)
                if db_session is None:
                    raise SessionNotFoundError(f"Session {session_id} not found")
            agent = self._agents[session_id]
            return agent.get_session_history()

        raise SessionNotFoundError(f"Session {session_id} not found")

    def _db_session_to_session_info(self, db_session: SessionModel) -> SessionInfo:
        """
        Convert a database Session model to SessionInfo dataclass.

        Args:
            db_session: SQLAlchemy Session model instance.

        Returns:
            SessionInfo dataclass with session details.
        """
        # Get video info from transcript relationship
        video_id = ""
        video_title = ""
        thumbnail_url = None
        if db_session.transcript:
            video_id = db_session.transcript.video_id
            video_title = db_session.transcript.title
            thumbnail_url = db_session.transcript.thumbnail_url

        return SessionInfo(
            session_id=db_session.id,
            transcript_id=db_session.transcript_id,
            video_id=video_id,
            video_title=video_title,
            thumbnail_url=thumbnail_url,
            model_provider=db_session.model_provider,
            model_id=db_session.model_name,
            created_at=db_session.created_at,
            last_activity=db_session.updated_at,
            query_count=len(db_session.messages) // 2 if db_session.messages else 0,
        )

    def _restore_session(self, db_session: SessionModel) -> SessionInfo:
        """
        Restore an agent session from database.

        Recreates the agent with conversation history loaded from the database.

        Args:
            db_session: SQLAlchemy Session model with transcript relationship.

        Returns:
            SessionInfo for the restored session.

        Raises:
            IndexingError: If transcript indexing fails.
            AgentNotAvailableError: If agent cannot be created.
        """
        self._ensure_available()

        transcript = db_session.transcript
        if not transcript:
            raise TranscriptNotFoundError(
                f"Transcript for session {db_session.id} not found"
            )

        session_id = db_session.id

        # Auto-index transcript if needed
        if not self.is_indexed(str(transcript.id)):
            logger.info("Auto-indexing transcript %s for restored session", transcript.id)
            self.index_transcript(str(transcript.id), user_id=str(db_session.user_id))

        # Create session info
        session_info = SessionInfo(
            session_id=session_id,
            transcript_id=str(transcript.id),
            video_id=transcript.video_id,
            video_title=transcript.title,
            thumbnail_url=transcript.thumbnail_url,
            model_provider=db_session.model_provider,
            model_id=db_session.model_name,
            created_at=db_session.created_at,
            last_activity=db_session.updated_at,
            query_count=len(db_session.messages) // 2 if db_session.messages else 0,
        )

        # Create agent instance with document knowledge base
        try:
            agent = TranscriptQueryAgent(
                transcript_id=str(transcript.id),
                video_title=transcript.title,
                video_id=transcript.video_id,
                channel_name=transcript.channel_name,
                duration_seconds=transcript.duration_seconds,
                session_id=session_id,
                model_provider=db_session.model_provider,
                config=self.config,
                document_knowledge_base=self.document_knowledge_base,
            )

            # Inject conversation history into agent
            if db_session.messages:
                for msg in db_session.messages:
                    agent.add_message_to_history(msg.role, msg.content)

        except AgentNotConfiguredError as e:
            raise AgentNotAvailableError(str(e)) from e
        except TranscriptNotIndexedError as e:
            raise IndexingError(str(e)) from e

        # Store in memory registries
        self._sessions[session_id] = session_info
        self._agents[session_id] = agent

        logger.info(
            "Restored session %s for transcript %s with %d messages",
            session_id,
            transcript.id,
            len(db_session.messages) if db_session.messages else 0,
        )

        return session_info
