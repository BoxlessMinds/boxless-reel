"""Service for extracting transcripts and metadata from YouTube videos."""

import logging
from typing import Any

import yt_dlp
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from src.config import settings
from src.services.exceptions import (
    TranscriptNotAvailableError,
    VideoNotFoundError,
    YouTubeServiceError,
)
from src.services.whisper_service import WhisperTranscriptionService
from src.utils.youtube_url_parser import extract_video_id as _extract_video_id

logger = logging.getLogger(__name__)


class YouTubeService:
    """Service for extracting transcripts and metadata from YouTube videos."""

    def extract_video_id(self, url_or_id: str) -> str:
        """
        Extract video ID from a YouTube URL or validate a raw video ID.

        Args:
            url_or_id: YouTube URL in various formats or an 11-character video ID.

        Returns:
            The 11-character video ID.

        Raises:
            InvalidVideoIdError: If the URL format is not recognized or video ID is invalid.
        """
        return _extract_video_id(url_or_id)

    def extract_transcript(self, video_id: str) -> dict[str, Any]:
        """
        Extract transcript from a YouTube video.

        Args:
            video_id: The 11-character YouTube video ID.

        Returns:
            Dictionary containing:
                - segments: List of transcript segments with text, start, and duration
                - full_text: Complete transcript as a single string
                - language: Language code of the transcript

        Raises:
            TranscriptNotAvailableError: If no English transcript is available.
            VideoNotFoundError: If the video is unavailable.
            YouTubeServiceError: For other extraction failures.
        """
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.list(video_id)

            # Try to get manually created English transcript first, then auto-generated
            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except NoTranscriptFound:
                transcript = transcript_list.find_generated_transcript(["en"])

            segments = transcript.fetch()

            return {
                "segments": [
                    {
                        "text": segment.text,
                        "start": segment.start,
                        "duration": segment.duration,
                    }
                    for segment in segments
                ],
                "full_text": " ".join(segment.text for segment in segments),
                "language": transcript.language_code,
                "source": "captions",
            }

        except TranscriptsDisabled:
            logger.warning("Transcripts disabled for video %s", video_id)
            raise TranscriptNotAvailableError(
                f"Transcripts are disabled for video {video_id}"
            )
        except NoTranscriptFound:
            logger.warning("No English transcript found for video %s", video_id)
            raise TranscriptNotAvailableError(
                f"No English transcript found for video {video_id}"
            )
        except VideoUnavailable:
            logger.warning("Video %s is unavailable", video_id)
            raise VideoNotFoundError(f"Video {video_id} is unavailable")
        except Exception as e:
            logger.exception("Failed to extract transcript for video %s", video_id)
            raise YouTubeServiceError(f"Failed to extract transcript: {e}") from e

    def extract_metadata(self, video_id: str) -> dict[str, Any]:
        """
        Extract video metadata using yt-dlp.

        Args:
            video_id: The 11-character YouTube video ID.

        Returns:
            Dictionary containing:
                - title: Video title
                - channel_name: Channel name (may be None)
                - thumbnail_url: Thumbnail URL (may be None)
                - duration_seconds: Video duration in seconds (may be None)

        Raises:
            VideoNotFoundError: If the video is unavailable or private.
            YouTubeServiceError: For other extraction failures.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            return {
                "title": info.get("title", "Unknown Title"),
                "channel_name": info.get("channel") or info.get("uploader"),
                "thumbnail_url": info.get("thumbnail"),
                "duration_seconds": info.get("duration"),
            }

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if "unavailable" in error_msg or "private" in error_msg:
                logger.warning("Video %s is unavailable or private", video_id)
                raise VideoNotFoundError(
                    f"Video {video_id} is unavailable or private"
                ) from e
            logger.exception("Failed to extract metadata for video %s", video_id)
            raise YouTubeServiceError(f"Failed to extract metadata: {e}") from e
        except Exception as e:
            logger.exception("Failed to extract metadata for video %s", video_id)
            raise YouTubeServiceError(f"Failed to extract metadata: {e}") from e

    def extract_all(self, url_or_id: str) -> dict[str, Any]:
        """
        Extract both transcript and metadata from a YouTube video.

        This is a convenience method that combines extract_video_id,
        extract_transcript, and extract_metadata into a single call.

        Args:
            url_or_id: YouTube URL or video ID.

        Returns:
            Dictionary containing:
                - video_id: The extracted video ID
                - title: Video title
                - channel_name: Channel name
                - thumbnail_url: Thumbnail URL
                - duration_seconds: Video duration
                - transcript_text: Full transcript text
                - transcript_segments: List of timestamped segments
                - language: Transcript language code

        Raises:
            InvalidVideoIdError: If the URL/ID format is invalid.
            VideoNotFoundError: If the video is unavailable.
            TranscriptNotAvailableError: If no English transcript is available.
            YouTubeServiceError: For other extraction failures.
        """
        video_id = self.extract_video_id(url_or_id)

        # Extract metadata first (usually faster and confirms video exists)
        metadata = self.extract_metadata(video_id)

        # Extract transcript, with Whisper fallback if captions are unavailable
        try:
            transcript_data = self.extract_transcript(video_id)
        except TranscriptNotAvailableError:
            if not settings.whisper_fallback_enabled or not settings.openai_api_key:
                raise

            duration = metadata.get("duration_seconds")
            if duration and duration > settings.whisper_max_duration_seconds:
                logger.warning(
                    "Video %s is %ds, exceeds Whisper max of %ds",
                    video_id, duration, settings.whisper_max_duration_seconds,
                )
                raise

            logger.info("Captions unavailable for %s, attempting Whisper fallback", video_id)
            whisper_service = WhisperTranscriptionService(
                api_key=settings.openai_api_key,
                model=settings.whisper_model,
                audio_bitrate=settings.whisper_audio_bitrate,
            )
            transcript_data = whisper_service.transcribe_from_video_id(video_id)

        return {
            "video_id": video_id,
            "title": metadata["title"],
            "channel_name": metadata["channel_name"],
            "thumbnail_url": metadata["thumbnail_url"],
            "duration_seconds": metadata["duration_seconds"],
            "transcript_text": transcript_data["full_text"],
            "transcript_segments": transcript_data["segments"],
            "language": transcript_data["language"],
            "source": transcript_data.get("source", "captions"),
        }
