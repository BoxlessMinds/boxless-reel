"""Cross-chat service for querying across multiple transcript sessions."""

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
    TranscriptKnowledgeBase,
)
from src.models.cross_chat_session import CrossChatSession as CrossChatSessionModel
from src.repositories.cross_chat_repository import CrossChatRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.transcript_repository import TranscriptRepository
from src.services.exceptions import (
    AgentNotAvailableError,
    CrossChatSessionNotFoundError,
    CrossChatValidationError,
    IndexingError,
    QueryExecutionError,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)

# Maximum number of cross-chat sessions to keep in memory
_MAX_REGISTRY_SIZE = 500


class _BoundedDict(OrderedDict):
    """OrderedDict with a maximum size — evicts oldest entries when full."""

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > _MAX_REGISTRY_SIZE:
            self.popitem(last=False)


# Module-level registries to persist cross-chat agents across service instances
_cross_chat_agents_registry: _BoundedDict = _BoundedDict()
_cross_chat_info_registry: _BoundedDict = _BoundedDict()


@dataclass
class CrossChatInfo:
    """In-memory info for an active cross-chat session."""

    cross_chat_id: str
    transcript_ids: list[str]
    video_titles: dict[str, str]
    video_ids: dict[str, str]
    model_provider: str
    model_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    query_count: int = 0


class CrossChatService:
    """
    Service layer for cross-chat transcript querying.

    Orchestrates:
    - Cross-chat session lifecycle management
    - Multi-transcript indexing coordination
    - Query execution across multiple transcripts via TranscriptQueryAgent
    """

    def __init__(
        self,
        cross_chat_repository: CrossChatRepository,
        session_repository: SessionRepository,
        transcript_repository: TranscriptRepository,
        config: AgentConfig | None = None,
    ) -> None:
        """
        Initialize the cross-chat service.

        Args:
            cross_chat_repository: Repository for cross-chat database operations.
            session_repository: Repository for agent session operations.
            transcript_repository: Repository for transcript operations.
            config: Agent configuration. Uses get_agent_config() if None.
        """
        self.cross_chat_repository = cross_chat_repository
        self.session_repository = session_repository
        self.transcript_repository = transcript_repository
        self.config = config or get_agent_config()

        self._agents = _cross_chat_agents_registry
        self._info = _cross_chat_info_registry

        self._knowledge_base: TranscriptKnowledgeBase | None = None

    @property
    def knowledge_base(self) -> TranscriptKnowledgeBase:
        """Get or create the shared transcript knowledge base instance."""
        if self._knowledge_base is None:
            self._knowledge_base = TranscriptKnowledgeBase(config=self.config)
        return self._knowledge_base

    def _ensure_available(self) -> None:
        """Ensure agent features are available."""
        if not self.config.is_enabled:
            raise AgentNotAvailableError(
                "Agent features require an LLM API key. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

    def create_session(
        self,
        session_ids: list[str],
        user_id: str,
        model_provider: str | None = None,
    ) -> CrossChatSessionModel:
        """
        Create a new cross-chat session spanning multiple agent sessions.

        Validates that all sessions exist and belong to the user,
        ensures transcripts are indexed, then creates the DB record.

        Args:
            session_ids: List of agent session IDs (minimum 2).
            user_id: UUID of the user creating the session.
            model_provider: LLM provider.

        Returns:
            CrossChatSession database model with relationships loaded.

        Raises:
            AgentNotAvailableError: If no LLM providers configured.
            CrossChatValidationError: If session_ids are invalid.
            IndexingError: If transcript indexing fails.
        """
        self._ensure_available()

        if len(session_ids) < 2:
            raise CrossChatValidationError("At least 2 session IDs are required.")

        # Validate all sessions exist and belong to user
        transcript_ids = []
        video_titles = {}
        video_ids = {}

        for sid in session_ids:
            agent_session = self.session_repository.get_with_transcript(sid, user_id=user_id)
            if agent_session is None:
                raise CrossChatValidationError(
                    f"Session {sid} not found or not owned by user."
                )
            if agent_session.transcript is None:
                raise CrossChatValidationError(
                    f"Session {sid} has no associated transcript."
                )

            tid = str(agent_session.transcript.id)
            transcript_ids.append(tid)
            video_titles[tid] = agent_session.transcript.title
            video_ids[tid] = agent_session.transcript.video_id

            # Ensure transcript is indexed
            if not self.knowledge_base.is_indexed(tid):
                logger.info("Auto-indexing transcript %s for cross-chat", tid)
                try:
                    self.knowledge_base.load_transcript(
                        transcript_id=tid,
                        transcript_text=agent_session.transcript.transcript_text,
                        transcript_segments=agent_session.transcript.transcript_segments,
                        video_id=agent_session.transcript.video_id,
                    )
                except Exception as e:
                    logger.error("Failed to index transcript %s: %s", tid, e)
                    raise IndexingError(f"Failed to index transcript: {e}") from e

        # Validate provider
        validated_provider = self.config.validate_provider(model_provider)
        model_id = self.config.get_model_id(validated_provider)

        # Create DB record
        db_session = self.cross_chat_repository.create(
            user_id=user_id,
            session_ids=session_ids,
            model_provider=validated_provider,
            model_name=model_id,
        )

        # Create in-memory info
        info = CrossChatInfo(
            cross_chat_id=db_session.id,
            transcript_ids=transcript_ids,
            video_titles=video_titles,
            video_ids=video_ids,
            model_provider=validated_provider,
            model_id=model_id,
        )
        self._info[db_session.id] = info

        # Create agent for cross-chat
        self._create_cross_chat_agent(db_session.id, info)

        logger.info(
            "Created cross-chat session %s with %d sessions (user=%s)",
            db_session.id,
            len(session_ids),
            user_id,
        )

        return db_session

    def _create_cross_chat_agent(
        self,
        cross_chat_id: str,
        info: CrossChatInfo,
    ) -> TranscriptQueryAgent:
        """
        Create a TranscriptQueryAgent configured for multi-transcript search.

        Args:
            cross_chat_id: The cross-chat session identifier.
            info: CrossChatInfo with transcript details.

        Returns:
            Configured TranscriptQueryAgent.
        """
        titles = list(info.video_titles.values())
        combined_title = " | ".join(titles)
        primary_tid = info.transcript_ids[0]
        primary_vid = info.video_ids.get(primary_tid, "")

        try:
            agent = TranscriptQueryAgent(
                transcript_id=primary_tid,
                video_title=f"Cross-Chat: {combined_title}",
                video_id=primary_vid,
                channel_name="Multiple Videos",
                duration_seconds=None,
                session_id=cross_chat_id,
                model_provider=info.model_provider,
                config=self.config,
                document_knowledge_base=None,
            )
        except AgentNotConfiguredError as e:
            raise AgentNotAvailableError(str(e)) from e
        except TranscriptNotIndexedError as e:
            raise IndexingError(str(e)) from e

        # Override the search tool to search across all transcripts
        self._override_search_tool(agent, info)

        self._agents[cross_chat_id] = agent
        return agent

    def _override_search_tool(
        self,
        agent: TranscriptQueryAgent,
        info: CrossChatInfo,
    ) -> None:
        """Replace the agent search tool with one that searches multiple transcripts."""
        from agno.tools import tool

        knowledge_base = self.knowledge_base
        transcript_ids = info.transcript_ids
        video_titles = info.video_titles
        max_results = self.config.max_context_chunks
        agent_ref = agent

        @tool
        def search_context(query: str) -> str:
            """Search across multiple video transcripts for relevant content.

            Use this tool to find specific information, quotes, or discussions
            across all referenced video transcripts. The search uses semantic
            similarity to find the most relevant passages from any of the videos.

            Args:
                query: The search query - what you are looking for.

            Returns:
                A list of relevant excerpts from transcripts with citations.
            """
            all_results = []

            # Search across all transcripts
            results = knowledge_base.search(
                query=query,
                transcript_id=transcript_ids,
                num_results=max_results,
            )
            agent_ref._last_search_results = results

            for result in results:
                title = video_titles.get(result.transcript_id, "Unknown Video")
                all_results.append(
                    f"[TRANSCRIPT: {title} @ {result.format_timestamp()}]" + chr(10) + result.text
                )

            if not all_results:
                return "No relevant content found across the transcripts."

            separator = chr(10) + chr(10) + "---" + chr(10) + chr(10)
            return separator.join(all_results)

        # Replace the tools on the underlying Agno agent
        new_tools = []
        for t in agent._agent.tools:
            name = getattr(t, "__name__", "") or getattr(t, "name", "")
            if name == "search_context":
                continue
            new_tools.append(t)
        new_tools.insert(0, search_context)
        agent._agent.tools = new_tools

    def query(
        self,
        cross_chat_id: str,
        user_id: str,
        question: str,
    ) -> dict[str, Any]:
        """
        Execute a query across multiple transcripts.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user who owns the session.
            question: The question to ask across transcripts.

        Returns:
            Dictionary with response content, citations, and metadata.

        Raises:
            CrossChatSessionNotFoundError: If session not found.
            QueryExecutionError: If query fails.
        """
        db_session = self._get_or_restore_session(cross_chat_id, user_id)

        if cross_chat_id not in self._agents:
            raise CrossChatSessionNotFoundError(
                f"Agent for cross-chat session {cross_chat_id} not found"
            )

        agent = self._agents[cross_chat_id]
        info = self._info.get(cross_chat_id)

        # Persist user message
        self.cross_chat_repository.add_message(
            cross_chat_id=cross_chat_id,
            role="user",
            content=question,
        )

        try:
            response: AgentResponse = agent.query(question)

            # Update in-memory info
            if info:
                info.last_activity = datetime.now(timezone.utc)
                info.query_count += 1

            # Build citations with video context
            citations = []
            for c in response.citations:
                citation_dict = c.to_dict()
                if c.source_type == "transcript" and info:
                    for sr in agent._last_search_results:
                        if abs(sr.start_time - (c.start_time or 0)) < 1:
                            citation_dict["video_id"] = info.video_ids.get(sr.transcript_id, "")
                            citation_dict["video_title"] = info.video_titles.get(sr.transcript_id, "")
                            break
                citations.append(citation_dict)

            # Persist assistant response
            self.cross_chat_repository.add_message(
                cross_chat_id=cross_chat_id,
                role="assistant",
                content=response.content,
                citations=citations,
            )

            return {
                "content": response.content,
                "citations": citations,
                "session_id": cross_chat_id,
                "model_used": response.model_used,
                "search_results_used": response.transcript_results_used,
                "created_at": response.created_at.isoformat(),
            }

        except QueryError as e:
            logger.error("Cross-chat query failed for session %s: %s", cross_chat_id, e)
            raise QueryExecutionError(f"Query failed: {e}") from e

    def get_session(self, cross_chat_id: str, user_id: str) -> CrossChatSessionModel:
        """
        Get a cross-chat session with messages and references.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user who owns the session.

        Returns:
            CrossChatSession model with relationships loaded.

        Raises:
            CrossChatSessionNotFoundError: If session not found.
        """
        db_session = self.cross_chat_repository.get_by_id(cross_chat_id, user_id)
        if db_session is None:
            raise CrossChatSessionNotFoundError(
                f"Cross-chat session {cross_chat_id} not found"
            )
        return db_session

    def list_sessions(self, user_id: str) -> list[CrossChatSessionModel]:
        """
        List all cross-chat sessions for a user.

        Args:
            user_id: UUID of the user.

        Returns:
            List of CrossChatSession models.
        """
        return self.cross_chat_repository.list_all(user_id)

    def delete_session(self, cross_chat_id: str, user_id: str) -> None:
        """
        Delete a cross-chat session.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user who owns the session.

        Raises:
            CrossChatSessionNotFoundError: If session not found.
        """
        deleted = self.cross_chat_repository.delete(cross_chat_id, user_id)
        if not deleted:
            raise CrossChatSessionNotFoundError(
                f"Cross-chat session {cross_chat_id} not found"
            )

        self._agents.pop(cross_chat_id, None)
        self._info.pop(cross_chat_id, None)

        logger.info("Deleted cross-chat session %s (user=%s)", cross_chat_id, user_id)

    def _get_or_restore_session(
        self,
        cross_chat_id: str,
        user_id: str,
    ) -> CrossChatSessionModel:
        """
        Get a cross-chat session, restoring the agent if needed.

        Args:
            cross_chat_id: The cross-chat session identifier.
            user_id: UUID of the user who owns the session.

        Returns:
            CrossChatSession model.

        Raises:
            CrossChatSessionNotFoundError: If session not found.
        """
        db_session = self.cross_chat_repository.get_by_id(cross_chat_id, user_id)
        if db_session is None:
            raise CrossChatSessionNotFoundError(
                f"Cross-chat session {cross_chat_id} not found"
            )

        if cross_chat_id not in self._agents:
            self._restore_agent(db_session)

        return db_session

    def _restore_agent(self, db_session: CrossChatSessionModel) -> None:
        """
        Restore a cross-chat agent from database state.

        Args:
            db_session: CrossChatSession model with relationships.
        """
        self._ensure_available()

        transcript_ids = []
        video_titles = {}
        video_ids = {}

        for ref in db_session.referenced_sessions:
            if ref.session and ref.session.transcript:
                transcript = ref.session.transcript
                tid = str(transcript.id)
                transcript_ids.append(tid)
                video_titles[tid] = transcript.title
                video_ids[tid] = transcript.video_id

                if not self.knowledge_base.is_indexed(tid):
                    logger.info("Auto-indexing transcript %s for restored cross-chat", tid)
                    self.knowledge_base.load_transcript(
                        transcript_id=tid,
                        transcript_text=transcript.transcript_text,
                        transcript_segments=transcript.transcript_segments,
                        video_id=transcript.video_id,
                    )

        info = CrossChatInfo(
            cross_chat_id=db_session.id,
            transcript_ids=transcript_ids,
            video_titles=video_titles,
            video_ids=video_ids,
            model_provider=db_session.model_provider,
            model_id=db_session.model_name,
            created_at=db_session.created_at,
            last_activity=db_session.updated_at,
            query_count=len(db_session.messages) // 2 if db_session.messages else 0,
        )
        self._info[db_session.id] = info

        agent = self._create_cross_chat_agent(db_session.id, info)

        if db_session.messages:
            for msg in db_session.messages:
                agent.add_message_to_history(msg.role, msg.content)

        logger.info(
            "Restored cross-chat session %s with %d transcripts and %d messages",
            db_session.id,
            len(transcript_ids),
            len(db_session.messages) if db_session.messages else 0,
        )
