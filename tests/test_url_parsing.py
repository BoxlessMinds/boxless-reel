"""Tests for YouTube URL parsing and video ID extraction."""

import pytest

from src.services import YouTubeService
from src.services.exceptions import InvalidVideoIdError


class TestExtractVideoId:
    """Tests for YouTubeService.extract_video_id method."""

    @pytest.fixture(autouse=True)
    def setup(self, youtube_service: YouTubeService) -> None:
        """Set up test fixtures."""
        self.service = youtube_service

    def test_full_youtube_url(self) -> None:
        """Test extraction from standard YouTube URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_short_youtu_be_url(self) -> None:
        """Test extraction from short youtu.be URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_url_with_timestamp(self) -> None:
        """Test extraction from URL with timestamp parameter."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_url_with_playlist(self) -> None:
        """Test extraction from URL with playlist parameter."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_url_without_www(self) -> None:
        """Test extraction from URL without www prefix."""
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_url_http_protocol(self) -> None:
        """Test extraction from HTTP URL (not HTTPS)."""
        url = "http://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_shorts_url(self) -> None:
        """Test extraction from a YouTube Shorts URL."""
        url = "https://youtube.com/shorts/dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_shorts_url_with_www(self) -> None:
        """Test extraction from a Shorts URL with the www prefix."""
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_shorts_url_with_si_param(self) -> None:
        """Test extraction from a Shorts URL with a trailing si= share parameter."""
        url = "https://youtube.com/shorts/dQw4w9WgXcQ?si=ahZCeI_x3deZUPvy"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_shorts_url_without_protocol(self) -> None:
        """Test extraction from a Shorts URL with no scheme."""
        url = "youtube.com/shorts/dQw4w9WgXcQ"
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_raw_video_id(self) -> None:
        """Test validation of raw 11-character video ID."""
        video_id = "dQw4w9WgXcQ"
        result = self.service.extract_video_id(video_id)
        assert result == "dQw4w9WgXcQ"

    def test_raw_video_id_with_underscores(self) -> None:
        """Test raw video ID containing underscores."""
        video_id = "abc_123_def"
        result = self.service.extract_video_id(video_id)
        assert result == "abc_123_def"

    def test_raw_video_id_with_hyphens(self) -> None:
        """Test raw video ID containing hyphens."""
        video_id = "abc-123-def"
        result = self.service.extract_video_id(video_id)
        assert result == "abc-123-def"

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is stripped from input."""
        video_id = "  dQw4w9WgXcQ  "
        result = self.service.extract_video_id(video_id)
        assert result == "dQw4w9WgXcQ"

    def test_whitespace_in_url(self) -> None:
        """Test that whitespace is stripped from URL input."""
        url = "  https://www.youtube.com/watch?v=dQw4w9WgXcQ  "
        result = self.service.extract_video_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_invalid_domain_raises_error(self) -> None:
        """Test that invalid domain raises InvalidVideoIdError."""
        url = "https://vimeo.com/123456789"
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id(url)
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_invalid_id_length_short(self) -> None:
        """Test that short video ID raises InvalidVideoIdError."""
        video_id = "abc123"
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id(video_id)
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_invalid_id_length_long(self) -> None:
        """Test that long video ID raises InvalidVideoIdError."""
        video_id = "dQw4w9WgXcQ123"
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id(video_id)
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_empty_string_raises_error(self) -> None:
        """Test that empty string raises InvalidVideoIdError."""
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id("")
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_whitespace_only_raises_error(self) -> None:
        """Test that whitespace-only string raises InvalidVideoIdError."""
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id("   ")
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_malformed_url_raises_error(self) -> None:
        """Test that malformed URL raises InvalidVideoIdError."""
        url = "https://youtube.com/watch?wrong=dQw4w9WgXcQ"
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id(url)
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)

    def test_url_with_invalid_characters(self) -> None:
        """Test URL with invalid characters in video ID position."""
        url = "https://youtube.com/watch?v=invalid!@#$"
        with pytest.raises(InvalidVideoIdError) as exc_info:
            self.service.extract_video_id(url)
        assert "Invalid YouTube URL or video ID" in str(exc_info.value)
