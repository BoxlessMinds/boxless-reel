"""Service for transcribing audio using the OpenAI Whisper API."""

import logging
import os
import shutil
import tempfile
from typing import Any

import yt_dlp
from openai import OpenAI

from src.services.exceptions import AudioDownloadError, WhisperTranscriptionError

logger = logging.getLogger(__name__)

# Whisper API file size limit (25MB)
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


class WhisperTranscriptionService:
    """Service for downloading audio and transcribing via OpenAI Whisper API."""

    def __init__(self, api_key: str, model: str = "whisper-1", audio_bitrate: str = "48k") -> None:
        """
        Initialize the Whisper transcription service.

        Args:
            api_key: OpenAI API key.
            model: Whisper model to use.
            audio_bitrate: Audio bitrate for mp3 compression (e.g., "48k").
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.audio_bitrate = audio_bitrate

    def transcribe_from_video_id(self, video_id: str) -> dict[str, Any]:
        """
        Download audio from a YouTube video and transcribe it via Whisper.

        Args:
            video_id: The 11-character YouTube video ID.

        Returns:
            Dictionary containing:
                - segments: List of transcript segments with text, start, and duration
                - full_text: Complete transcript as a single string
                - language: Detected language code
                - source: "whisper"

        Raises:
            AudioDownloadError: If audio download fails.
            WhisperTranscriptionError: If Whisper API call fails or file is too large.
        """
        temp_dir = tempfile.mkdtemp(prefix="whisper_")
        try:
            audio_path = self._download_audio(video_id, temp_dir)
            return self._transcribe_audio(audio_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _download_audio(self, video_id: str, temp_dir: str) -> str:
        """
        Download audio from a YouTube video using yt-dlp.

        Args:
            video_id: The 11-character YouTube video ID.
            temp_dir: Temporary directory for the downloaded file.

        Returns:
            Path to the downloaded audio file.

        Raises:
            AudioDownloadError: If the download or conversion fails.
        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.audio_bitrate.rstrip("k"),
                }
            ],
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            # The "web" client increasingly returns 403s on the actual media
            # download without a PO token; "android"/"ios" clients serve
            # formats that don't require one, so try those first.
            "extractor_args": {
                "youtube": {"player_client": ["android", "ios", "web"]}
            },
        }

        try:
            logger.info("Downloading audio for video %s", video_id)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.exception("Failed to download audio for video %s", video_id)
            raise AudioDownloadError(f"Failed to download audio for video {video_id}: {e}") from e

        # Find the downloaded mp3 file
        for filename in os.listdir(temp_dir):
            if filename.endswith(".mp3"):
                return os.path.join(temp_dir, filename)

        raise AudioDownloadError(f"No mp3 file found after download for video {video_id}")

    def _transcribe_audio(self, audio_path: str) -> dict[str, Any]:
        """
        Transcribe an audio file using the OpenAI Whisper API.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Dictionary with segments, full_text, language, and source.

        Raises:
            WhisperTranscriptionError: If the file is too large or the API call fails.
        """
        file_size = os.path.getsize(audio_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            size_mb = file_size / (1024 * 1024)
            raise WhisperTranscriptionError(
                f"Audio file is {size_mb:.1f}MB, exceeds Whisper API limit of 25MB. "
                "Try a shorter video."
            )

        try:
            logger.info("Transcribing audio file (%d bytes) via Whisper API", file_size)
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except Exception as e:
            logger.exception("Whisper API transcription failed")
            raise WhisperTranscriptionError(f"Whisper API transcription failed: {e}") from e

        segments = [
            {
                "text": seg.text.strip(),
                "start": seg.start,
                "duration": seg.end - seg.start,
            }
            for seg in (response.segments or [])
        ]

        return {
            "segments": segments,
            "full_text": response.text.strip(),
            "language": response.language or "en",
            "source": "whisper",
        }
