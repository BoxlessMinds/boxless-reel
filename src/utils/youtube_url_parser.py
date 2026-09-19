"""Parsing helpers for turning pasted YouTube URLs into video/playlist IDs.

Generalizes the URL/ID regexes that originally lived on
`src.services.youtube_service.YouTubeService.extract_video_id` (watch?v=,
youtu.be/, shorts/, bare 11-char IDs) to also cover embed/ and live/ links,
plus a `list=` playlist-ID extractor for the add-by-URL flow.
`YouTubeService.extract_video_id` now delegates here.
"""

import re

from src.services.exceptions import InvalidVideoIdError

# Path-based YouTube video URL formats: watch?v=, youtu.be/, shorts/,
# embed/, live/. Query-string suffixes (e.g. &t=, &list=, ?si=) are ignored
# since the video ID is anchored right after the recognized path segment.
YOUTUBE_URL_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.)?"
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)"
    r"([\w-]{11})"
)

# Raw video ID: 11 characters, letters/numbers/underscores/hyphens.
VIDEO_ID_PATTERN = re.compile(r"^[\w-]{11}$")

# `list=` query parameter, as found on a playlist page URL
# (youtube.com/playlist?list=PLxxxx) or appended to a video URL.
PLAYLIST_ID_PATTERN = re.compile(r"[?&]list=([\w-]+)")


def extract_video_id(url_or_id: str) -> str:
    """
    Extract a video ID from a YouTube URL, or validate a raw video ID.

    Args:
        url_or_id: YouTube URL in any recognized format, or an
            11-character video ID.

    Returns:
        The 11-character video ID.

    Raises:
        InvalidVideoIdError: If the URL format is not recognized or the
            video ID is invalid.
    """
    value = url_or_id.strip()

    if VIDEO_ID_PATTERN.match(value):
        return value

    match = YOUTUBE_URL_PATTERN.search(value)
    if match:
        return match.group(1)

    raise InvalidVideoIdError(
        f"Invalid YouTube URL or video ID: {url_or_id}. "
        "Expected formats: youtube.com/watch?v=VIDEO_ID, youtube.com/shorts/VIDEO_ID, "
        "youtube.com/embed/VIDEO_ID, youtube.com/live/VIDEO_ID, youtu.be/VIDEO_ID, "
        "or a raw 11-character ID."
    )


def extract_playlist_id(url: str) -> str | None:
    """
    Extract a playlist ID from a YouTube URL's `list=` query parameter.

    Args:
        url: A YouTube URL, e.g. `youtube.com/playlist?list=PLxxxx` or a
            video URL with a trailing `&list=PLxxxx`.

    Returns:
        The playlist ID, or None if no `list=` parameter is present.
    """
    match = PLAYLIST_ID_PATTERN.search(url.strip())
    return match.group(1) if match else None
