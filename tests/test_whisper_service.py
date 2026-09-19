"""Tests for WhisperTranscriptionService and Whisper fallback orchestration."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.services.exceptions import (
    AudioDownloadError,
    TranscriptNotAvailableError,
    WhisperTranscriptionError,
)
from src.services.whisper_service import WhisperTranscriptionService


class TestWhisperTranscriptionService:
    """Unit tests for WhisperTranscriptionService."""

    @pytest.fixture
    def whisper_service(self):
        """Create a WhisperTranscriptionService with a fake API key."""
        with patch("src.services.whisper_service.OpenAI"):
            service = WhisperTranscriptionService(
                api_key="test-key", model="whisper-1", audio_bitrate="48k"
            )
        return service

    @pytest.fixture
    def mock_whisper_response(self):
        """Create a mock Whisper API verbose_json response."""
        response = MagicMock()
        response.text = "Hello world. This is a test."
        response.language = "en"

        seg1 = MagicMock()
        seg1.text = "Hello world."
        seg1.start = 0.0
        seg1.end = 2.5

        seg2 = MagicMock()
        seg2.text = "This is a test."
        seg2.start = 2.5
        seg2.end = 5.0

        response.segments = [seg1, seg2]
        return response

    def test_transcribe_from_video_id_success(self, whisper_service, mock_whisper_response):
        """Test successful audio download and transcription."""
        with (
            patch.object(whisper_service, "_download_audio", return_value="/tmp/test.mp3"),
            patch.object(whisper_service, "_transcribe_audio") as mock_transcribe,
            patch("src.services.whisper_service.shutil.rmtree") as mock_rmtree,
            patch("src.services.whisper_service.tempfile.mkdtemp", return_value="/tmp/whisper_test"),
        ):
            mock_transcribe.return_value = {
                "segments": [
                    {"text": "Hello world.", "start": 0.0, "duration": 2.5},
                ],
                "full_text": "Hello world.",
                "language": "en",
                "source": "whisper",
            }

            result = whisper_service.transcribe_from_video_id("test1234567")

            assert result["source"] == "whisper"
            assert result["full_text"] == "Hello world."
            assert len(result["segments"]) == 1
            mock_rmtree.assert_called_once_with("/tmp/whisper_test", ignore_errors=True)

    def test_transcribe_cleans_up_on_failure(self, whisper_service):
        """Test that temp directory is cleaned up even when transcription fails."""
        with (
            patch.object(
                whisper_service, "_download_audio", side_effect=AudioDownloadError("fail")
            ),
            patch("src.services.whisper_service.shutil.rmtree") as mock_rmtree,
            patch("src.services.whisper_service.tempfile.mkdtemp", return_value="/tmp/whisper_fail"),
        ):
            with pytest.raises(AudioDownloadError):
                whisper_service.transcribe_from_video_id("test1234567")

            mock_rmtree.assert_called_once_with("/tmp/whisper_fail", ignore_errors=True)

    def test_transcribe_audio_converts_response(self, whisper_service, mock_whisper_response):
        """Test that Whisper response is correctly converted to our segment format."""
        whisper_service.client.audio.transcriptions.create.return_value = mock_whisper_response

        with patch("src.services.whisper_service.os.path.getsize", return_value=1024):
            with patch("builtins.open", mock_open()):
                result = whisper_service._transcribe_audio("/tmp/test.mp3")

        assert result["source"] == "whisper"
        assert result["full_text"] == "Hello world. This is a test."
        assert result["language"] == "en"
        assert len(result["segments"]) == 2
        assert result["segments"][0] == {"text": "Hello world.", "start": 0.0, "duration": 2.5}
        assert result["segments"][1] == {"text": "This is a test.", "start": 2.5, "duration": 2.5}

    def test_transcribe_audio_rejects_large_files(self, whisper_service):
        """Test that files exceeding 25MB are rejected."""
        large_size = 26 * 1024 * 1024  # 26MB

        with patch("src.services.whisper_service.os.path.getsize", return_value=large_size):
            with pytest.raises(WhisperTranscriptionError, match="exceeds Whisper API limit"):
                whisper_service._transcribe_audio("/tmp/large.mp3")

    def test_transcribe_audio_api_error(self, whisper_service):
        """Test that Whisper API errors are wrapped in WhisperTranscriptionError."""
        whisper_service.client.audio.transcriptions.create.side_effect = Exception("API error")

        with patch("src.services.whisper_service.os.path.getsize", return_value=1024):
            with patch("builtins.open", mock_open()):
                with pytest.raises(WhisperTranscriptionError, match="API error"):
                    whisper_service._transcribe_audio("/tmp/test.mp3")

    def test_download_audio_failure(self, whisper_service):
        """Test that yt-dlp download failures raise AudioDownloadError."""
        with patch("src.services.whisper_service.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__ = MagicMock()
            mock_ydl.return_value.__exit__ = MagicMock(return_value=False)
            mock_ydl.return_value.__enter__.return_value.download.side_effect = Exception("download failed")

            with pytest.raises(AudioDownloadError, match="download failed"):
                whisper_service._download_audio("test1234567", "/tmp/test_dir")

    def test_download_audio_no_mp3_found(self, whisper_service):
        """Test error when no mp3 file is produced after download."""
        with (
            patch("src.services.whisper_service.yt_dlp.YoutubeDL") as mock_ydl,
            patch("src.services.whisper_service.os.listdir", return_value=["test.webm"]),
        ):
            mock_ctx = MagicMock()
            mock_ydl.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ydl.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(AudioDownloadError, match="No mp3 file found"):
                whisper_service._download_audio("test1234567", "/tmp/test_dir")


class TestWhisperFallbackOrchestration:
    """Tests for the Whisper fallback logic in YouTubeService.extract_all()."""

    @pytest.fixture
    def youtube_service(self):
        """Return a real YouTubeService instance."""
        from src.services.youtube_service import YouTubeService
        return YouTubeService()

    def test_captions_succeed_no_whisper(self, youtube_service):
        """When captions are available, Whisper should not be called."""
        with (
            patch.object(youtube_service, "extract_video_id", return_value="test1234567"),
            patch.object(youtube_service, "extract_metadata", return_value={
                "title": "Test", "channel_name": "Ch", "thumbnail_url": None, "duration_seconds": 60,
            }),
            patch.object(youtube_service, "extract_transcript", return_value={
                "segments": [], "full_text": "Hello", "language": "en", "source": "captions",
            }),
            patch("src.services.youtube_service.WhisperTranscriptionService") as mock_whisper,
        ):
            result = youtube_service.extract_all("test1234567")

            assert result["source"] == "captions"
            mock_whisper.assert_not_called()

    def test_captions_fail_whisper_fallback(self, youtube_service):
        """When captions fail and Whisper is enabled, fallback should trigger."""
        with (
            patch.object(youtube_service, "extract_video_id", return_value="test1234567"),
            patch.object(youtube_service, "extract_metadata", return_value={
                "title": "Test", "channel_name": "Ch", "thumbnail_url": None, "duration_seconds": 60,
            }),
            patch.object(
                youtube_service, "extract_transcript",
                side_effect=TranscriptNotAvailableError("No captions"),
            ),
            patch("src.services.youtube_service.settings") as mock_settings,
            patch("src.services.youtube_service.WhisperTranscriptionService") as mock_whisper_cls,
        ):
            mock_settings.whisper_fallback_enabled = True
            mock_settings.openai_api_key = "test-key"
            mock_settings.whisper_model = "whisper-1"
            mock_settings.whisper_audio_bitrate = "48k"
            mock_settings.whisper_max_duration_seconds = 3600

            mock_whisper_instance = MagicMock()
            mock_whisper_instance.transcribe_from_video_id.return_value = {
                "segments": [{"text": "Hello", "start": 0.0, "duration": 2.0}],
                "full_text": "Hello",
                "language": "en",
                "source": "whisper",
            }
            mock_whisper_cls.return_value = mock_whisper_instance

            result = youtube_service.extract_all("test1234567")

            assert result["source"] == "whisper"
            mock_whisper_cls.assert_called_once_with(
                api_key="test-key", model="whisper-1", audio_bitrate="48k",
            )
            mock_whisper_instance.transcribe_from_video_id.assert_called_once_with("test1234567")

    def test_fallback_skipped_when_disabled(self, youtube_service):
        """When whisper_fallback_enabled is False, original error should propagate."""
        with (
            patch.object(youtube_service, "extract_video_id", return_value="test1234567"),
            patch.object(youtube_service, "extract_metadata", return_value={
                "title": "Test", "channel_name": "Ch", "thumbnail_url": None, "duration_seconds": 60,
            }),
            patch.object(
                youtube_service, "extract_transcript",
                side_effect=TranscriptNotAvailableError("No captions"),
            ),
            patch("src.services.youtube_service.settings") as mock_settings,
        ):
            mock_settings.whisper_fallback_enabled = False
            mock_settings.openai_api_key = "test-key"

            with pytest.raises(TranscriptNotAvailableError):
                youtube_service.extract_all("test1234567")

    def test_fallback_skipped_when_no_api_key(self, youtube_service):
        """When openai_api_key is None, original error should propagate."""
        with (
            patch.object(youtube_service, "extract_video_id", return_value="test1234567"),
            patch.object(youtube_service, "extract_metadata", return_value={
                "title": "Test", "channel_name": "Ch", "thumbnail_url": None, "duration_seconds": 60,
            }),
            patch.object(
                youtube_service, "extract_transcript",
                side_effect=TranscriptNotAvailableError("No captions"),
            ),
            patch("src.services.youtube_service.settings") as mock_settings,
        ):
            mock_settings.whisper_fallback_enabled = True
            mock_settings.openai_api_key = None

            with pytest.raises(TranscriptNotAvailableError):
                youtube_service.extract_all("test1234567")

    def test_fallback_skipped_when_video_too_long(self, youtube_service):
        """When video duration exceeds max, original error should propagate."""
        with (
            patch.object(youtube_service, "extract_video_id", return_value="test1234567"),
            patch.object(youtube_service, "extract_metadata", return_value={
                "title": "Test", "channel_name": "Ch", "thumbnail_url": None, "duration_seconds": 7200,
            }),
            patch.object(
                youtube_service, "extract_transcript",
                side_effect=TranscriptNotAvailableError("No captions"),
            ),
            patch("src.services.youtube_service.settings") as mock_settings,
        ):
            mock_settings.whisper_fallback_enabled = True
            mock_settings.openai_api_key = "test-key"
            mock_settings.whisper_max_duration_seconds = 3600

            with pytest.raises(TranscriptNotAvailableError):
                youtube_service.extract_all("test1234567")
