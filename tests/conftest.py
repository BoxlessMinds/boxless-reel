"""Pytest configuration and fixtures for testing."""

import os

# Must be set before src.config is imported. An obviously fake value, used only in tests.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-not-a-real-secret-" + "0" * 36)

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models.transcript import Transcript
from src.models.user import User
from src.dependencies.auth import get_current_user
from src.services import AgentService, YouTubeService
from src.services.agent_service import _sessions_registry, _agents_registry

# Pre-computed bcrypt hash for "testpassword123" - avoids bcrypt compatibility issues in tests
# This is equivalent to bcrypt.hashpw(b"testpassword123", bcrypt.gensalt())
TEST_PASSWORD_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.gK.QhYA5sDqAru"


# Test database setup - in-memory SQLite
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Use StaticPool for in-memory database
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def clear_session_registries() -> Generator[None, None, None]:
    """
    Clear module-level session registries before and after each test.

    This ensures test isolation for session-related tests.
    """
    _sessions_registry.clear()
    _agents_registry.clear()
    yield
    _sessions_registry.clear()
    _agents_registry.clear()


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """
    Create a fresh database session for each test.

    Creates all tables before the test and drops them after.
    """
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create and return a test user for authentication tests."""
    user = User(
        id=str(uuid4()),
        email="test@example.com",
        display_name="Test User",
        password_hash=TEST_PASSWORD_HASH,
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_admin(test_db: Session) -> User:
    """Create and return a test admin user."""
    user = User(
        id=str(uuid4()),
        email="admin@example.com",
        display_name="Admin User",
        password_hash=TEST_PASSWORD_HASH,
        role="admin",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def client(test_db: Session, test_user: User) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with test database and authenticated user.

    Overrides the get_db dependency to use the test database session
    and the get_current_user dependency to return the test user.
    """

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    # Clear dependency overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(test_db: Session, test_admin: User) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with test database and authenticated admin user.
    """

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    def override_get_current_user() -> User:
        return test_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    # Clear dependency overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def sample_transcript_data() -> dict[str, Any]:
    """Return sample transcript data for creating test records."""
    return {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video Title",
        "channel_name": "Test Channel",
        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg",
        "transcript_text": "This is a test transcript text.",
        "transcript_segments": [
            {"text": "This is a test", "start": 0.0, "duration": 2.5},
            {"text": "transcript text.", "start": 2.5, "duration": 2.0},
        ],
        "language": "en",
        "duration_seconds": 212,
    }


@pytest.fixture
def existing_transcript(test_db: Session, test_user: User, sample_transcript_data: dict[str, Any]) -> Transcript:
    """Create and return a transcript in the test database."""
    sample_transcript_data["user_id"] = test_user.id
    transcript = Transcript(**sample_transcript_data)
    test_db.add(transcript)
    test_db.commit()
    test_db.refresh(transcript)
    return transcript


@pytest.fixture
def multiple_transcripts(test_db: Session, test_user: User) -> list[Transcript]:
    """Create multiple transcripts for pagination and filtering tests."""
    transcripts_data = [
        {
            "video_id": "video00001a",
            "title": "Python Tutorial",
            "channel_name": "Code Channel",
            "transcript_text": "Learn Python programming basics.",
            "transcript_segments": [{"text": "Learn Python", "start": 0.0, "duration": 2.0}],
            "language": "en",
            "user_id": test_user.id,
        },
        {
            "video_id": "video00002b",
            "title": "JavaScript Guide",
            "channel_name": "Web Dev",
            "transcript_text": "JavaScript fundamentals explained.",
            "transcript_segments": [{"text": "JavaScript", "start": 0.0, "duration": 2.0}],
            "language": "en",
            "user_id": test_user.id,
        },
        {
            "video_id": "video00003c",
            "title": "Spanish Lesson",
            "channel_name": "Language School",
            "transcript_text": "Aprende espanol facilmente.",
            "transcript_segments": [{"text": "Aprende espanol", "start": 0.0, "duration": 2.0}],
            "language": "es",
            "user_id": test_user.id,
        },
    ]

    transcripts = []
    for data in transcripts_data:
        transcript = Transcript(**data)
        test_db.add(transcript)
        test_db.commit()
        test_db.refresh(transcript)
        transcripts.append(transcript)

    return transcripts


@pytest.fixture
def mock_youtube_service() -> Generator[MagicMock, None, None]:
    """Mock YouTubeService for testing without external API calls."""
    # Patch where YouTubeService is instantiated (in the services __init__.py)
    with patch("src.services.YouTubeService") as mock_class:
        mock_instance = MagicMock(spec=YouTubeService)

        # Default: extract_video_id returns the video ID from the URL
        def mock_extract_video_id(url_or_id: str) -> str:
            """Extract video ID from URL or return as-is if valid."""
            url_or_id = url_or_id.strip()
            # Simple extraction for test URLs
            if "v=" in url_or_id:
                return url_or_id.split("v=")[1].split("&")[0]
            if "youtu.be/" in url_or_id:
                return url_or_id.split("youtu.be/")[1].split("?")[0]
            return url_or_id

        mock_instance.extract_video_id.side_effect = mock_extract_video_id

        # Default successful extraction response
        mock_instance.extract_all.return_value = {
            "video_id": "newvideo123",
            "title": "New Test Video",
            "channel_name": "Test Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/newvideo123/default.jpg",
            "duration_seconds": 300,
            "transcript_text": "New transcript content here.",
            "transcript_segments": [
                {"text": "New transcript", "start": 0.0, "duration": 3.0},
                {"text": "content here.", "start": 3.0, "duration": 2.0},
            ],
            "language": "en",
        }

        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def youtube_service() -> YouTubeService:
    """Return a real YouTubeService instance for unit testing."""
    return YouTubeService()


@pytest.fixture
def mock_agent_service() -> Generator[MagicMock, None, None]:
    """Mock AgentService for testing without LLM/embedding API calls."""
    # Patch where AgentService is instantiated (in the services __init__.py)
    with patch("src.services.AgentService") as mock_class:
        mock_instance = MagicMock(spec=AgentService)

        # Default: index_transcript returns chunk count
        mock_instance.index_transcript.return_value = 5

        # Default: is_indexed returns False
        mock_instance.is_indexed.return_value = False

        mock_class.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Cross-Chat Fixtures
# =============================================================================


@pytest.fixture
def multiple_chat_sessions(
    test_db: Session, test_user: User, multiple_transcripts: list[Transcript]
) -> list:
    """Create multiple chat sessions linked to transcripts for cross-chat testing.

    Returns a list of at least 2 ChatSession objects, each associated with a
    different transcript owned by the test_user.
    """
    from src.models.session import Session as ChatSession

    sessions = []
    for transcript in multiple_transcripts[:2]:
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
        sessions.append(session)
    return sessions


@pytest.fixture
def cross_chat_session(
    test_db: Session, test_user: User, multiple_chat_sessions: list
):
    """Create a CrossChatSession with references to existing chat sessions.

    Depends on multiple_chat_sessions to ensure there are valid sessions
    to reference. Returns the persisted CrossChatSession object.
    """
    try:
        from src.models.cross_chat_session import (
            CrossChatSession,
            CrossChatSessionReference,
        )
    except ImportError:
        pytest.skip("CrossChatSession model not implemented yet")

    cross = CrossChatSession(
        id=str(uuid4()),
        model_provider="anthropic",
        model_name="claude-sonnet-4-5-20250929",
        user_id=test_user.id,
    )
    test_db.add(cross)
    test_db.commit()
    test_db.refresh(cross)

    for session in multiple_chat_sessions:
        ref = CrossChatSessionReference(
            cross_chat_session_id=cross.id,
            session_id=session.id,
        )
        test_db.add(ref)

    test_db.commit()
    test_db.refresh(cross)
    return cross
