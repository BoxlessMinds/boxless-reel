"""Tests for API endpoints."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.transcript import Transcript
from src.services.exceptions import (
    InvalidVideoIdError,
    TranscriptAlreadyExistsError,
    TranscriptNotAvailableError,
    VideoNotFoundError,
    YouTubeServiceError,
)


class TestExtractEndpoint:
    """Tests for POST /api/transcripts/extract endpoint."""

    def test_extract_success(
        self, client: TestClient, mock_youtube_service: MagicMock, mock_agent_service: MagicMock
    ) -> None:
        """Test successful transcript extraction."""
        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://www.youtube.com/watch?v=newvideo123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["video_id"] == "newvideo123"
        assert data["title"] == "New Test Video"
        assert data["channel_name"] == "Test Channel"
        assert data["transcript_text"] == "New transcript content here."
        assert len(data["transcript_segments"]) == 2
        assert "id" in data
        assert "created_at" in data

    def test_extract_invalid_url_format(self, client: TestClient) -> None:
        """Test that invalid URL format returns 422."""
        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://invalid-url.com/video"},
        )

        # Pydantic validation fails before reaching the service
        assert response.status_code == 422

    def test_extract_video_not_found(
        self, client: TestClient, mock_youtube_service: MagicMock
    ) -> None:
        """Test that unavailable video returns 404."""
        mock_youtube_service.extract_all.side_effect = VideoNotFoundError(
            "Video not found"
        )

        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://www.youtube.com/watch?v=deletedvid1"},
        )

        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]

    def test_extract_transcript_not_available(
        self, client: TestClient, mock_youtube_service: MagicMock
    ) -> None:
        """Test that video without transcript returns 404."""
        mock_youtube_service.extract_all.side_effect = TranscriptNotAvailableError(
            "No transcript available"
        )

        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://www.youtube.com/watch?v=notranscri1"},
        )

        assert response.status_code == 404
        assert "No transcript available" in response.json()["detail"]

    def test_extract_duplicate_video(
        self,
        client: TestClient,
        mock_youtube_service: MagicMock,
        existing_transcript: Transcript,
    ) -> None:
        """Test that duplicate video returns 409."""
        # The mock won't be called because service checks DB first
        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": f"https://www.youtube.com/watch?v={existing_transcript.video_id}"},
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_extract_invalid_video_id(
        self, client: TestClient, mock_youtube_service: MagicMock
    ) -> None:
        """Test that invalid video ID returns 400."""
        mock_youtube_service.extract_all.side_effect = InvalidVideoIdError(
            "Invalid video ID"
        )

        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://www.youtube.com/watch?v=invalid1234"},
        )

        assert response.status_code == 400
        assert "Invalid video ID" in response.json()["detail"]

    def test_extract_service_error(
        self, client: TestClient, mock_youtube_service: MagicMock
    ) -> None:
        """Test that service error returns 500."""
        mock_youtube_service.extract_all.side_effect = YouTubeServiceError(
            "Service unavailable"
        )

        response = client.post(
            "/api/transcripts/extract",
            json={"youtube_url": "https://www.youtube.com/watch?v=errorvid123"},
        )

        assert response.status_code == 500
        assert "Service unavailable" in response.json()["detail"]


class TestListEndpoint:
    """Tests for GET /api/transcripts endpoint."""

    def test_list_empty(self, client: TestClient) -> None:
        """Test listing when no transcripts exist."""
        response = client.get("/api/transcripts")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["total_pages"] == 0

    def test_list_with_transcripts(
        self, client: TestClient, multiple_transcripts: list[Transcript]
    ) -> None:
        """Test listing with existing transcripts."""
        response = client.get("/api/transcripts")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == len(multiple_transcripts)
        assert data["total"] == len(multiple_transcripts)

    def test_list_items_format(
        self, client: TestClient, existing_transcript: Transcript
    ) -> None:
        """Test that list items have correct format."""
        response = client.get("/api/transcripts")

        assert response.status_code == 200
        item = response.json()["items"][0]

        # List items should have basic fields but not full transcript
        assert "id" in item
        assert "video_id" in item
        assert "title" in item
        assert "channel_name" in item
        assert "language" in item
        assert "created_at" in item
        # List items may or may not include transcript_text based on schema

    def test_list_with_search(
        self, client: TestClient, multiple_transcripts: list[Transcript]
    ) -> None:
        """Test search filter."""
        response = client.get("/api/transcripts", params={"search": "Python"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Python" in data["items"][0]["title"]

    def test_list_with_language_filter(
        self, client: TestClient, multiple_transcripts: list[Transcript]
    ) -> None:
        """Test language filter."""
        response = client.get("/api/transcripts", params={"language": "es"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["language"] == "es"

    def test_list_pagination(
        self, client: TestClient, multiple_transcripts: list[Transcript]
    ) -> None:
        """Test pagination parameters."""
        response = client.get(
            "/api/transcripts", params={"page": 1, "page_size": 2}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total"] == 3
        assert data["total_pages"] == 2

    def test_list_page_two(
        self, client: TestClient, multiple_transcripts: list[Transcript]
    ) -> None:
        """Test accessing second page."""
        response = client.get(
            "/api/transcripts", params={"page": 2, "page_size": 2}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["page"] == 2

    def test_list_invalid_page_size(self, client: TestClient) -> None:
        """Test that page_size over 100 is rejected."""
        response = client.get(
            "/api/transcripts", params={"page_size": 101}
        )

        assert response.status_code == 422

    def test_list_invalid_page_number(self, client: TestClient) -> None:
        """Test that page 0 is rejected."""
        response = client.get("/api/transcripts", params={"page": 0})

        assert response.status_code == 422


class TestGetEndpoint:
    """Tests for GET /api/transcripts/{id} endpoint."""

    def test_get_existing_transcript(
        self, client: TestClient, existing_transcript: Transcript
    ) -> None:
        """Test getting an existing transcript by ID."""
        response = client.get(f"/api/transcripts/{existing_transcript.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == existing_transcript.id
        assert data["video_id"] == existing_transcript.video_id
        assert data["title"] == existing_transcript.title
        assert data["transcript_text"] == existing_transcript.transcript_text
        assert "transcript_segments" in data

    def test_get_nonexistent_transcript(self, client: TestClient) -> None:
        """Test that non-existent ID returns 404."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/transcripts/{fake_uuid}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteEndpoint:
    """Tests for DELETE /api/transcripts/{id} endpoint."""

    def test_delete_existing_transcript(
        self, client: TestClient, existing_transcript: Transcript
    ) -> None:
        """Test deleting an existing transcript."""
        transcript_id = existing_transcript.id

        response = client.delete(f"/api/transcripts/{transcript_id}")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

        # Verify transcript is gone
        get_response = client.get(f"/api/transcripts/{transcript_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_transcript(self, client: TestClient) -> None:
        """Test that deleting non-existent ID returns 404."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"

        response = client.delete(f"/api/transcripts/{fake_uuid}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test health check endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
