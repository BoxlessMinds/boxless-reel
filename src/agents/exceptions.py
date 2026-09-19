"""Agent-specific exceptions."""


class AgentError(Exception):
    """Base exception for agent errors."""

    pass


class AgentNotConfiguredError(AgentError):
    """
    Raised when agent features are not configured.

    This typically means no LLM API keys are set in the environment.
    """

    pass


class TranscriptNotIndexedError(AgentError):
    """
    Raised when attempting to query a transcript that hasn't been indexed.

    The transcript must be indexed in the knowledge base before it can
    be queried by the agent.
    """

    pass


class SessionNotFoundError(AgentError):
    """
    Raised when a session ID does not exist.

    This occurs when trying to continue a conversation with an
    invalid or expired session ID.
    """

    pass


class QueryError(AgentError):
    """
    Raised when a query fails to execute.

    This can occur due to LLM API errors, timeout, or other
    runtime failures during query processing.
    """

    pass
