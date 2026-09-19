"""Tests for src.utils.youtube_url_parser -- generalized URL/ID
and playlist-ID parsing, covering every format in scope (watch?v=,
youtu.be/, shorts/, embed/, live/, bare 11-char ID) plus rejection of a
malformed entry.
"""

import pytest

from src.services.exceptions import InvalidVideoIdError
from src.utils.youtube_url_parser import extract_playlist_id, extract_video_id


class TestExtractVideoId:
    """Every listed URL format resolves to the correct video_id (AC1)."""

    def test_watch_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_without_www(self) -> None:
        assert extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_youtu_be_url(self) -> None:
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self) -> None:
        assert extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url_with_si_param(self) -> None:
        url = "https://youtube.com/shorts/dQw4w9WgXcQ?si=ahZCeI_x3deZUPvy"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url_without_www(self) -> None:
        assert extract_video_id("https://youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url_without_protocol(self) -> None:
        assert extract_video_id("youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_bare_video_id(self) -> None:
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_whitespace_is_stripped(self) -> None:
        assert extract_video_id("  dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"

    def test_malformed_url_is_rejected(self) -> None:
        with pytest.raises(InvalidVideoIdError):
            extract_video_id("https://vimeo.com/123456789")

    def test_malformed_id_length_is_rejected(self) -> None:
        with pytest.raises(InvalidVideoIdError):
            extract_video_id("short")

    def test_playlist_page_url_alone_is_rejected(self) -> None:
        """A pure playlist page URL (no v=) has no video ID at all."""
        with pytest.raises(InvalidVideoIdError):
            extract_video_id("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")


class TestExtractPlaylistId:
    """Playlist-ID extraction backing AC2's list= expansion."""

    def test_playlist_page_url(self) -> None:
        url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_playlist_id(url) == "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    def test_watch_url_with_list_param(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_playlist_id(url) == "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    def test_no_list_param_returns_none(self) -> None:
        assert extract_playlist_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None

    def test_bare_video_id_returns_none(self) -> None:
        assert extract_playlist_id("dQw4w9WgXcQ") is None
