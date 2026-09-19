"""Tests for YouTubeDataService (read-only YouTube Data API v3 wrapper).

Every `googleapiclient` call is mocked here — no test in this module
reaches the network or spends real YouTube Data API quota.
"""

import json
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.services.youtube_data_service import (
    PermanentAPIError,
    QuotaExceededError,
    YouTubeDataService,
    YouTubeDataServiceError,
)


def _http_error(status: int, reason: str, message: str = "error") -> HttpError:
    """Build a real googleapiclient HttpError with a Google-shaped error body."""
    content = json.dumps(
        {
            "error": {
                "errors": [{"reason": reason, "message": message}],
                "code": status,
                "message": message,
            }
        }
    ).encode("utf-8")
    return HttpError(httplib2.Response({"status": status}), content)


@pytest.fixture
def mock_client() -> MagicMock:
    """A MagicMock standing in for the googleapiclient `youtube` resource."""
    with patch("src.services.youtube_data_service.build") as mock_build:
        client = MagicMock()
        mock_build.return_value = client
        yield client


@pytest.fixture
def data_service(mock_client: MagicMock) -> YouTubeDataService:
    """A YouTubeDataService wired to the mocked client."""
    return YouTubeDataService(MagicMock())


class TestListMyPlaylists:
    """`playlists.list` pagination, retry, and error classification."""

    def test_paginates_until_no_next_page_token(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "PL1"}], "nextPageToken": "TOKEN2"},
            {"items": [{"id": "PL2"}]},
        ]

        pages = list(data_service.list_my_playlists())

        assert pages == [[{"id": "PL1"}], [{"id": "PL2"}]]
        assert mock_client.playlists.return_value.list.call_count == 2

    def test_retries_transient_error_then_succeeds(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        transient = _http_error(503, "backendError")
        mock_client.playlists.return_value.list.return_value.execute.side_effect = [
            transient,
            {"items": [{"id": "PL1"}]},
        ]

        with patch("time.sleep"):
            pages = list(data_service.list_my_playlists())

        assert pages == [[{"id": "PL1"}]]
        assert mock_client.playlists.return_value.list.return_value.execute.call_count == 2

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            list(data_service.list_my_playlists())

        assert mock_client.playlists.return_value.list.return_value.execute.call_count == 1

    def test_permanent_error_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(404, "notFound")
        )

        with pytest.raises(YouTubeDataServiceError):
            list(data_service.list_my_playlists())

        assert mock_client.playlists.return_value.list.return_value.execute.call_count == 1


class TestListPlaylistItems:
    """`playlistItems.list` pagination and error classification."""

    def test_paginates_items(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "IT1"}], "nextPageToken": "T2"},
            {"items": [{"id": "IT2"}]},
        ]

        pages = list(data_service.list_playlist_items("PL1"))

        assert pages == [[{"id": "IT1"}], [{"id": "IT2"}]]
        assert mock_client.playlistItems.return_value.list.call_count == 2

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.list.return_value.execute.side_effect = (
            _http_error(403, "dailyLimitExceeded")
        )

        with pytest.raises(QuotaExceededError):
            list(data_service.list_playlist_items("PL1"))

        assert (
            mock_client.playlistItems.return_value.list.return_value.execute.call_count
            == 1
        )


class TestPermanentAPIErrorReclassification:
    """A non-quota 4xx now raises the more specific `PermanentAPIError`
    instead of the generic `YouTubeDataServiceError` -- needed so
    the plan apply executor can skip just the offending op rather than halt
    the whole plan. `PermanentAPIError` is a `YouTubeDataServiceError`
    subclass, so this does not change any assertion in the classes above."""

    def test_404_raises_permanent_api_error(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(404, "notFound")
        )

        with pytest.raises(PermanentAPIError):
            list(data_service.list_my_playlists())

    def test_400_raises_permanent_api_error(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(400, "invalidValue")
        )

        with pytest.raises(PermanentAPIError):
            list(data_service.list_my_playlists())

    def test_403_quota_exceeded_still_raises_quota_exceeded_not_permanent(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            list(data_service.list_my_playlists())


class TestInsertPlaylist:
    """`playlists.insert` request shape, response mapping, and error classification."""

    def test_inserts_and_returns_created_playlist_fields(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.insert.return_value.execute.return_value = {
            "id": "PL_NEW_123",
            "snippet": {"title": "My Playlist", "description": "A description"},
            "status": {"privacyStatus": "private"},
        }

        result = data_service.insert_playlist(
            title="My Playlist", description="A description", privacy_status="private"
        )

        assert result == {
            "youtube_playlist_id": "PL_NEW_123",
            "title": "My Playlist",
            "description": "A description",
            "privacy_status": "private",
        }
        mock_client.playlists.return_value.insert.assert_called_once_with(
            part="snippet,status",
            body={
                "snippet": {"title": "My Playlist", "description": "A description"},
                "status": {"privacyStatus": "private"},
            },
        )

    def test_permanent_error_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.insert.return_value.execute.side_effect = (
            _http_error(400, "invalidValue")
        )

        with pytest.raises(PermanentAPIError):
            data_service.insert_playlist(
                title="Bad", description=None, privacy_status="not-a-real-status"
            )

        assert mock_client.playlists.return_value.insert.return_value.execute.call_count == 1

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.insert.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            data_service.insert_playlist(
                title="My Playlist", description=None, privacy_status="private"
            )

        assert mock_client.playlists.return_value.insert.return_value.execute.call_count == 1


class TestGetPlaylist:
    """`playlists.list(id=...)` single-playlist lookup, not scoped to
    `mine=True`."""

    def test_returns_first_item_when_found(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "PL_PUBLIC_1", "snippet": {"title": "Public Mix"}}]
        }

        result = data_service.get_playlist("PL_PUBLIC_1")

        assert result == {"id": "PL_PUBLIC_1", "snippet": {"title": "Public Mix"}}
        mock_client.playlists.return_value.list.assert_called_once_with(
            part="snippet,status,contentDetails", id="PL_PUBLIC_1", maxResults=1
        )

    def test_returns_none_when_no_items(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        assert data_service.get_playlist("PL_GONE") is None

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlists.return_value.list.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            data_service.get_playlist("PL_1")


class TestInsertPlaylistItem:
    """`playlistItems.insert` request shape (both a bare-string and a
    whole ref-resolved-dict `playlist_id`), response mapping, and error
    classification."""

    def test_inserts_with_bare_string_playlist_id(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.insert.return_value.execute.return_value = {
            "id": "PLI_NEW_1",
            "snippet": {
                "playlistId": "PL_EXISTING",
                "position": 3,
                "resourceId": {"kind": "youtube#video", "videoId": "vidAAAAAAAA"},
            },
        }

        result = data_service.insert_playlist_item(
            playlist_id="PL_EXISTING", video_id="vidAAAAAAAA"
        )

        assert result == {
            "youtube_playlist_item_id": "PLI_NEW_1",
            "playlist_id": "PL_EXISTING",
            "video_id": "vidAAAAAAAA",
            "position": 3,
        }
        mock_client.playlistItems.return_value.insert.assert_called_once_with(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": "PL_EXISTING",
                    "resourceId": {"kind": "youtube#video", "videoId": "vidAAAAAAAA"},
                }
            },
        )

    def test_inserts_with_ref_resolved_whole_dict_playlist_id(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        """`plan_apply_service._resolve_value` substitutes an op's entire
        persisted `result`, not a single field -- when a copy plan's
        insert_playlist_item op references a prior insert_playlist op via
        a ref, this method receives the whole created-playlist dict, not a
        bare ID string."""
        mock_client.playlistItems.return_value.insert.return_value.execute.return_value = {
            "id": "PLI_NEW_2",
            "snippet": {
                "playlistId": "PL_NEW_777",
                "position": 0,
                "resourceId": {"kind": "youtube#video", "videoId": "vidBBBBBBBB"},
            },
        }

        result = data_service.insert_playlist_item(
            playlist_id={
                "youtube_playlist_id": "PL_NEW_777", "title": "Brand New Mix",
                "description": None, "privacy_status": "private",
            },
            video_id="vidBBBBBBBB",
        )

        assert result["playlist_id"] == "PL_NEW_777"
        mock_client.playlistItems.return_value.insert.assert_called_once_with(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": "PL_NEW_777",
                    "resourceId": {"kind": "youtube#video", "videoId": "vidBBBBBBBB"},
                }
            },
        )

    def test_permanent_error_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.insert.return_value.execute.side_effect = (
            _http_error(404, "playlistNotFound")
        )

        with pytest.raises(PermanentAPIError):
            data_service.insert_playlist_item(playlist_id="PL_GONE", video_id="vidAAAAAAAA")

        assert (
            mock_client.playlistItems.return_value.insert.return_value.execute.call_count
            == 1
        )

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.insert.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            data_service.insert_playlist_item(playlist_id="PL_1", video_id="vidAAAAAAAA")


class TestDeletePlaylistItem:
    """`playlistItems.delete` request shape, response synthesis, and error
    classification."""

    def test_deletes_and_returns_confirmation(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.delete.return_value.execute.return_value = None

        result = data_service.delete_playlist_item(playlist_item_id="PLI_123")

        assert result == {"playlist_item_id": "PLI_123", "deleted": True}
        mock_client.playlistItems.return_value.delete.assert_called_once_with(id="PLI_123")

    def test_permanent_error_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.delete.return_value.execute.side_effect = (
            _http_error(404, "playlistItemNotFound")
        )

        with pytest.raises(PermanentAPIError):
            data_service.delete_playlist_item(playlist_item_id="PLI_GONE")

        assert (
            mock_client.playlistItems.return_value.delete.return_value.execute.call_count
            == 1
        )

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.delete.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            data_service.delete_playlist_item(playlist_item_id="PLI_123")


class TestUpdatePlaylistItemPosition:
    """`playlistItems.update` request shape, response mapping, and error
    classification."""

    def test_updates_and_returns_new_position(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.update.return_value.execute.return_value = {
            "id": "PLI_123",
            "snippet": {
                "playlistId": "PL_EXISTING",
                "position": 5,
                "resourceId": {"kind": "youtube#video", "videoId": "vidAAAAAAAA"},
            },
        }

        result = data_service.update_playlist_item_position(
            playlist_item_id="PLI_123",
            playlist_id="PL_EXISTING",
            video_id="vidAAAAAAAA",
            position=5,
        )

        assert result == {
            "youtube_playlist_item_id": "PLI_123",
            "playlist_id": "PL_EXISTING",
            "video_id": "vidAAAAAAAA",
            "position": 5,
        }
        mock_client.playlistItems.return_value.update.assert_called_once_with(
            part="snippet",
            body={
                "id": "PLI_123",
                "snippet": {
                    "playlistId": "PL_EXISTING",
                    "resourceId": {"kind": "youtube#video", "videoId": "vidAAAAAAAA"},
                    "position": 5,
                },
            },
        )

    def test_permanent_error_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.update.return_value.execute.side_effect = (
            _http_error(404, "playlistItemNotFound")
        )

        with pytest.raises(PermanentAPIError):
            data_service.update_playlist_item_position(
                playlist_item_id="PLI_GONE",
                playlist_id="PL_EXISTING",
                video_id="vidAAAAAAAA",
                position=0,
            )

        assert (
            mock_client.playlistItems.return_value.update.return_value.execute.call_count
            == 1
        )

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.playlistItems.return_value.update.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            data_service.update_playlist_item_position(
                playlist_item_id="PLI_123",
                playlist_id="PL_EXISTING",
                video_id="vidAAAAAAAA",
                position=1,
            )


class TestListVideosBatch:
    """`videos.list` batching (VIDEOS_BATCH_SIZE per call) and per-batch
    result mapping (the enrichment pass)."""

    def test_single_batch_maps_video_id_to_resource(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {"id": "vid1", "status": {"uploadStatus": "processed"}},
                {"id": "vid2", "status": {"uploadStatus": "processed"}},
            ]
        }

        batches = list(data_service.list_videos_batch(["vid1", "vid2"]))

        assert batches == [
            {
                "vid1": {"id": "vid1", "status": {"uploadStatus": "processed"}},
                "vid2": {"id": "vid2", "status": {"uploadStatus": "processed"}},
            }
        ]
        mock_client.videos.return_value.list.assert_called_once_with(
            part="status", id="vid1,vid2", maxResults=50
        )

    def test_missing_video_id_is_absent_from_result(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "vid1", "status": {"uploadStatus": "processed"}}]
        }

        batches = list(data_service.list_videos_batch(["vid1", "vid_gone"]))

        assert "vid_gone" not in batches[0]
        assert "vid1" in batches[0]

    def test_batches_video_ids_by_fifty(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        video_ids = [f"vid{i:08d}" for i in range(75)]
        mock_client.videos.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": vid} for vid in video_ids[:50]]},
            {"items": [{"id": vid} for vid in video_ids[50:]]},
        ]

        batches = list(data_service.list_videos_batch(video_ids))

        assert len(batches) == 2
        assert len(batches[0]) == 50
        assert len(batches[1]) == 25
        assert mock_client.videos.return_value.list.call_count == 2

    def test_quota_exceeded_raises_without_retry(
        self, mock_client: MagicMock, data_service: YouTubeDataService
    ) -> None:
        mock_client.videos.return_value.list.return_value.execute.side_effect = (
            _http_error(403, "quotaExceeded")
        )

        with pytest.raises(QuotaExceededError):
            list(data_service.list_videos_batch(["vid1"]))
