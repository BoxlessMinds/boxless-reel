"""Custom exceptions for YouTube service operations."""


class YouTubeServiceError(Exception):
    """Base exception for YouTube service errors."""
    pass


class VideoNotFoundError(YouTubeServiceError):
    """Raised when video is unavailable, private, or deleted."""
    pass


class TranscriptNotAvailableError(YouTubeServiceError):
    """Raised when video has no transcript available."""
    pass


class InvalidVideoIdError(YouTubeServiceError):
    """Raised when video ID format is invalid."""
    pass


class TranscriptAlreadyExistsError(YouTubeServiceError):
    """Raised when attempting to extract a transcript that already exists."""
    pass


class AudioDownloadError(YouTubeServiceError):
    """Raised when yt-dlp fails to download audio from a video."""
    pass


class WhisperTranscriptionError(YouTubeServiceError):
    """Raised when the OpenAI Whisper API fails to transcribe audio."""
    pass


# Agent Service Exceptions


class AgentServiceError(Exception):
    """Base exception for agent service errors."""
    pass


class AgentNotAvailableError(AgentServiceError):
    """
    Raised when agent features are not available.

    This occurs when no LLM API keys are configured.
    Maps to HTTP 503 Service Unavailable.
    """
    pass


class SessionNotFoundError(AgentServiceError):
    """
    Raised when a session ID does not exist.

    Maps to HTTP 404 Not Found.
    """
    pass


class TranscriptNotFoundError(AgentServiceError):
    """
    Raised when the transcript ID does not exist in database.

    Maps to HTTP 404 Not Found.
    """
    pass


class IndexingError(AgentServiceError):
    """
    Raised when transcript indexing fails.

    Maps to HTTP 500 Internal Server Error.
    """
    pass


class QueryExecutionError(AgentServiceError):
    """
    Raised when a query fails to execute.

    Maps to HTTP 500 Internal Server Error.
    """
    pass


# Cross-Chat Exceptions


class CrossChatSessionNotFoundError(AgentServiceError):
    """
    Raised when a cross-chat session ID does not exist.

    Maps to HTTP 404 Not Found.
    """
    pass


class CrossChatValidationError(AgentServiceError):
    """
    Raised when cross-chat session creation validation fails.

    Maps to HTTP 400 Bad Request.
    """
    pass
