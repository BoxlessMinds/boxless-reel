"""Transcript Query Agent for answering questions about YouTube transcripts."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.tools import tool
from agno.tools.tavily import TavilyTools

from src.agents.config import AgentConfig, AgentConfigurationError, get_agent_config
from src.agents.exceptions import (
    AgentNotConfiguredError,
    QueryError,
    TranscriptNotIndexedError,
)
from src.agents.knowledge import (
    ChunkResult,
    DocumentChunkResult,
    DocumentKnowledgeBase,
    TranscriptKnowledgeBase,
)
from src.agents.prompts import (
    AGENT_INSTRUCTIONS,
    format_search_results,
    format_system_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """
    A citation from transcript, document, or web source.

    Attributes:
        text: The quoted or referenced text.
        source_type: Either "transcript", "document", or "web".
        start_time: Start timestamp in seconds (transcript only).
        end_time: End timestamp in seconds (transcript only).
        timestamp_formatted: Human-readable timestamp (transcript only).
        document_id: Document UUID (document only).
        document_name: Original filename (document only).
        page_number: Page number (document only).
        url: Source URL (web only).
        title: Page title (web only).
    """

    text: str
    source_type: Literal["transcript", "document", "web"] = "transcript"

    # Transcript fields
    start_time: float | None = None
    end_time: float | None = None
    timestamp_formatted: str = ""

    # Document fields
    document_id: str | None = None
    document_name: str | None = None
    page_number: int | None = None

    # Web fields
    url: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        """Set formatted timestamp for transcript citations."""
        if self.source_type == "transcript" and self.start_time is not None:
            if not self.timestamp_formatted:
                minutes = int(self.start_time // 60)
                seconds = int(self.start_time % 60)
                self.timestamp_formatted = f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = {
            "text": self.text,
            "source_type": self.source_type,
        }

        if self.source_type == "transcript":
            base.update({
                "start_time": self.start_time,
                "end_time": self.end_time,
                "timestamp_formatted": self.timestamp_formatted,
            })
        elif self.source_type == "document":
            base.update({
                "document_id": self.document_id,
                "document_name": self.document_name,
                "page_number": self.page_number,
            })
        else:
            base.update({
                "url": self.url,
                "title": self.title,
            })

        return base


@dataclass
class AgentResponse:
    """
    Response from the Transcript Query Agent.

    Attributes:
        content: The agent's response text.
        citations: List of citations from transcript, document, and/or web sources.
        session_id: Session identifier for conversation continuity.
        model_used: The LLM model that generated the response.
        transcript_results_used: Number of transcript search results used.
        document_results_used: Number of document search results used.
        web_results_used: Number of web search results used.
        created_at: Timestamp of response creation.
    """

    content: str
    citations: list[Citation] = field(default_factory=list)
    session_id: str | None = None
    model_used: str = ""
    transcript_results_used: int = 0
    document_results_used: int = 0
    web_results_used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "citations": [c.to_dict() for c in self.citations],
            "session_id": self.session_id,
            "model_used": self.model_used,
            "transcript_results_used": self.transcript_results_used,
            "document_results_used": self.document_results_used,
            "web_results_used": self.web_results_used,
            "created_at": self.created_at.isoformat(),
        }


class TranscriptQueryAgent:
    """
    Agent specialized for answering questions about YouTube transcripts.

    Features:
    - Agentic RAG: Searches transcript knowledge base on demand
    - Conversation memory: Maintains multi-turn context via session storage
    - Citation: References specific timestamps from the video
    - Grounded responses: Only answers based on transcript content

    Usage:
        agent = TranscriptQueryAgent(
            transcript_id="abc123",
            video_title="Python Tutorial",
            video_id="dQw4w9WgXcQ",
        )
        response = agent.query("What topics are covered?")
        print(response.content)
    """

    # Default database file for session storage
    DEFAULT_SESSION_DB = "data/agent_sessions.db"

    def __init__(
        self,
        transcript_id: str,
        video_title: str,
        video_id: str,
        channel_name: str | None = None,
        duration_seconds: int | None = None,
        session_id: str | None = None,
        model_provider: str | None = None,
        config: AgentConfig | None = None,
        document_knowledge_base: DocumentKnowledgeBase | None = None,
    ) -> None:
        """
        Initialize the Transcript Query Agent.

        Args:
            transcript_id: UUID of the transcript to query.
            video_title: Title of the YouTube video.
            video_id: YouTube video ID.
            channel_name: Channel name (optional).
            duration_seconds: Video duration (optional).
            session_id: Existing session ID for conversation continuity.
            model_provider: LLM provider ("anthropic" or "openai").
            config: Agent configuration. Uses get_agent_config() if None.
            document_knowledge_base: Optional knowledge base for document search.

        Raises:
            AgentNotConfiguredError: If no LLM provider is configured.
            TranscriptNotIndexedError: If transcript is not indexed.
        """
        self.config = config or get_agent_config()

        # Verify agent features are enabled
        if not self.config.is_enabled:
            raise AgentNotConfiguredError(
                "Agent features require at least one LLM API key. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
            )

        self.transcript_id = transcript_id
        self.video_id = video_id
        self.video_title = video_title
        self.channel_name = channel_name
        self.duration_seconds = duration_seconds
        self.session_id = session_id

        # Initialize knowledge bases
        self.knowledge_base = TranscriptKnowledgeBase(config=self.config)
        self.document_knowledge_base = document_knowledge_base

        # Verify transcript is indexed
        if not self.knowledge_base.is_indexed(transcript_id):
            raise TranscriptNotIndexedError(
                f"Transcript {transcript_id} has not been indexed. "
                "Index it first using TranscriptKnowledgeBase.load_transcript()."
            )

        # Store search results for citation extraction
        self._last_search_results: list[ChunkResult] = []
        self._last_document_results: list[DocumentChunkResult] = []
        self._last_web_results: list[dict[str, Any]] = []

        # Validate and get provider
        try:
            self._provider = self.config.validate_provider(model_provider)
        except AgentConfigurationError as e:
            raise AgentNotConfiguredError(str(e)) from e

        # Create the Agno Agent
        self._agent = self._create_agent()

        logger.info(
            "Initialized TranscriptQueryAgent for transcript %s with provider %s (documents=%s)",
            transcript_id,
            self._provider,
            "enabled" if document_knowledge_base else "disabled",
        )

    def _create_agent(self) -> Agent:
        """
        Create and configure the Agno Agent instance.

        Returns:
            Configured Agent instance.
        """
        # Create model using config helper
        model = self.config.create_model(self._provider)

        # Create session storage
        session_db = SqliteDb(
            id="transcript_agent",
            db_file=self.DEFAULT_SESSION_DB,
        )

        # Format system prompt with video metadata
        system_prompt = format_system_prompt(
            title=self.video_title,
            channel=self.channel_name,
            duration_seconds=self.duration_seconds,
        )

        # Create tools list - always include transcript search
        tools = [self._create_search_tool()]

        # Add Tavily web search if available
        if self.config.is_web_search_available:
            tavily_tools = TavilyTools(
                api_key=self.config.tavily_api_key,
                enable_search=True,
            )
            tools.append(tavily_tools)

        # Build instructions based on available tools
        instructions = self._build_instructions()

        # Build agent
        return Agent(
            name="Transcript Assistant",
            model=model,
            description=system_prompt,
            instructions=instructions,
            tools=tools,
            db=session_db,
            add_history_to_context=True,
            num_history_runs=10,
            markdown=True,
            session_id=self.session_id,
        )

    def _create_search_tool(self):
        """
        Create a tool function for searching the transcript and documents.

        Returns:
            Tool-decorated function for combined search.
        """
        # Capture references for closure
        knowledge_base = self.knowledge_base
        document_kb = self.document_knowledge_base
        transcript_id = self.transcript_id
        session_id = self.session_id
        max_results = self.config.max_context_chunks
        agent_ref = self  # Reference for storing results

        @tool
        def search_context(query: str) -> str:
            """Search the transcript and uploaded documents for relevant content.

            Use this tool to find specific information, quotes, or discussions
            in the video transcript and any uploaded documents. The search uses
            semantic similarity to find the most relevant passages.

            Args:
                query: The search query - what you're looking for.

            Returns:
                A list of relevant excerpts from transcript and documents with citations.
            """
            all_results = []

            # Search transcript (allocate ~60% of results)
            transcript_results_limit = max(3, int(max_results * 0.6))
            transcript_results = knowledge_base.search(
                query=query,
                transcript_id=transcript_id,
                num_results=transcript_results_limit,
            )
            agent_ref._last_search_results = transcript_results

            # Format transcript results
            for result in transcript_results:
                all_results.append(
                    f"[TRANSCRIPT @ {result.format_timestamp()}]\n{result.text}"
                )

            # Search documents if available (allocate ~40% of results)
            if document_kb and session_id:
                document_results_limit = max(2, max_results - transcript_results_limit)
                document_results = document_kb.search(
                    query=query,
                    session_id=session_id,
                    num_results=document_results_limit,
                )
                agent_ref._last_document_results = document_results

                # Format document results
                for result in document_results:
                    location = result.format_location()
                    all_results.append(
                        f"[DOCUMENT: {result.document_name} - {location}]\n{result.text}"
                    )
            else:
                agent_ref._last_document_results = []

            if not all_results:
                return "No relevant content found for the query."

            return "\n\n---\n\n".join(all_results)

        return search_context

    def _build_instructions(self) -> list[str]:
        """
        Build agent instructions based on available tools.

        Returns:
            List of instruction strings for the agent.
        """
        # Base instructions from the prompts module
        base_instructions = list(AGENT_INSTRUCTIONS)

        # Add document search instructions if documents are available
        if self.document_knowledge_base and self.session_id:
            doc_instructions = [
                "You have access to both the video transcript AND uploaded documents.",
                "The search_context tool searches both sources simultaneously.",
                "Results from documents are marked with [DOCUMENT: filename - Page X].",
                "Results from the transcript are marked with [TRANSCRIPT @ MM:SS].",
                "Cite document sources by filename and page number when referencing them.",
                "Cite transcript sources by timestamp when referencing them.",
            ]
            base_instructions.extend(doc_instructions)

        # Add web search instructions if Tavily is available
        if self.config.is_web_search_available:
            web_instructions = [
                "You also have access to web search (tavily_search) for supplementary information.",
                "Use web search ONLY when context search doesn't provide sufficient information.",
                "Web search is useful for: fact verification, background context, current events, external references.",
                "Always cite web sources with their URLs when using web search results.",
                "Clearly distinguish between transcript/document content and web information in your responses.",
            ]
            base_instructions.extend(web_instructions)

        return base_instructions

    def query(self, question: str) -> AgentResponse:
        """
        Process a user query and return a response.

        Args:
            question: The user's question about the transcript.

        Returns:
            AgentResponse with content, citations, and metadata.

        Raises:
            QueryError: If the query fails to execute.
        """
        logger.debug("Processing query: %s", question[:100])

        # Reset search results
        self._last_search_results = []
        self._last_document_results = []
        self._last_web_results = []

        try:
            # Run the agent
            result = self._agent.run(question)

            # Extract response content
            content = ""
            if hasattr(result, "content") and result.content:
                content = result.content
            elif hasattr(result, "messages") and result.messages:
                # Get the last assistant message
                for msg in reversed(result.messages):
                    if hasattr(msg, "role") and msg.role == "assistant":
                        if hasattr(msg, "content") and msg.content:
                            content = msg.content
                            break

            if not content:
                content = str(result)

            # Build citations from search results
            citations = self._extract_citations()

            # Get model info
            model_id = self.config.get_model_id(self._provider)

            # Update session_id from result if available
            if hasattr(result, "session_id") and result.session_id:
                self.session_id = result.session_id

            response = AgentResponse(
                content=content,
                citations=citations,
                session_id=self.session_id,
                model_used=model_id,
                transcript_results_used=len(self._last_search_results),
                document_results_used=len(self._last_document_results),
                web_results_used=len(self._last_web_results),
            )

            logger.info(
                "Query completed with %d citations from %d transcript + %d document + %d web results",
                len(citations),
                len(self._last_search_results),
                len(self._last_document_results),
                len(self._last_web_results),
            )

            return response

        except Exception as e:
            logger.error("Query failed: %s", e)
            raise QueryError(f"Failed to process query: {e}") from e

    def _extract_citations(self) -> list[Citation]:
        """
        Extract citations from transcript, document, and web search results.

        Returns:
            List of Citation objects from all sources.
        """
        citations = []

        # Transcript citations
        for result in self._last_search_results:
            # Truncate long text for citations
            text = result.text
            if len(text) > 200:
                text = text[:200] + "..."

            citations.append(
                Citation(
                    text=text,
                    source_type="transcript",
                    start_time=result.start_time,
                    end_time=result.end_time,
                )
            )

        # Document citations
        for result in self._last_document_results:
            text = result.text
            if len(text) > 200:
                text = text[:200] + "..."

            citations.append(
                Citation(
                    text=text,
                    source_type="document",
                    document_id=result.document_id,
                    document_name=result.document_name,
                    page_number=result.page_number,
                )
            )

        # Web citations
        for result in self._last_web_results:
            content = result.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."

            citations.append(
                Citation(
                    text=content,
                    source_type="web",
                    url=result.get("url"),
                    title=result.get("title"),
                )
            )

        return citations

    def get_session_history(self) -> list[dict[str, Any]]:
        """
        Retrieve the conversation history for this session.

        Returns:
            List of message dictionaries with role and content.
        """
        if not self.session_id:
            return []

        try:
            # Try to get session from storage
            if hasattr(self._agent, "get_session_messages"):
                messages = self._agent.get_session_messages(self.session_id)
                if messages:
                    return [
                        {
                            "role": getattr(msg, "role", "unknown"),
                            "content": getattr(msg, "content", str(msg)),
                        }
                        for msg in messages
                    ]
        except Exception as e:
            logger.warning("Failed to retrieve session history: %s", e)

        return []

    def add_message_to_history(self, role: str, content: str) -> None:
        """
        Add a message to the agent's conversation history.

        Used to restore conversation context when resuming a session
        from the database after a server restart.

        Args:
            role: Message role ("user" or "assistant").
            content: Message content.
        """
        if not self.session_id:
            logger.warning("Cannot add message to history without session_id")
            return

        try:
            # Access the agent's memory directly
            if hasattr(self._agent, "memory") and self._agent.memory:
                from agno.memory import Message as AgnoMessage

                msg = AgnoMessage(role=role, content=content)
                self._agent.memory.add_message(msg)
                logger.debug("Added %s message to agent memory", role)
            elif hasattr(self._agent, "db") and self._agent.db:
                # Alternative: Add directly to session storage
                # This requires knowing Agno's internal storage format
                logger.debug(
                    "Agent has db but no memory interface, skipping history injection"
                )
        except Exception as e:
            # Log but don't fail - the agent will still work, just without full history
            logger.warning("Failed to add message to agent history: %s", e)

    @property
    def model_provider(self) -> str:
        """Get the current model provider."""
        return self._provider

    @property
    def model_id(self) -> str:
        """Get the current model ID."""
        return self.config.get_model_id(self._provider)
