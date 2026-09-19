"""Tests for PlaylistSyncService (F1 sync + local cache).

The YouTube Data API is fully mocked via a stand-in for `YouTubeDataService`
— no test in this module reaches the network or spends real quota. Google
OAuth is likewise mocked via a stand-in for `GoogleAuthService`; only the
repository/quota layers hit a real (in-memory) database, so upsert
idempotency and quota-ledger writes are exercised for real.
"""

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.playlist import QuotaLedgerEntry
from src.models.user import User
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.quota_repository import QuotaRepository
from src.services.playlist_sync_service import PlaylistSyncService
from src.services.quota_service import QuotaService

PAGE_SIZE = 50


def _video_id(index: int) -> str:
    """An 11-character fake video ID, unique per index."""
    return f"v{index:010d}"


def _raw_playlist(playlist_id: str, title: str, item_count: int = 0) -> dict[str, Any]:
    """Build a raw `playlists.list` item resource."""
    return {
        "id": playlist_id,
        "snippet": {"title": title, "description": f"{title} description"},
        "status": {"privacyStatus": "private"},
        "contentDetails": {"itemCount": item_count},
    }


def _raw_item(
    item_id: str,
    video_id: str,
    title: str = "Some Video",
    position: int = 0,
    privacy_status: str = "public",
) -> dict[str, Any]:
    """Build a raw `playlistItems.list` item resource."""
    return {
        "id": item_id,
        "snippet": {
            "title": title,
            "channelTitle": "Some Channel",
            "position": position,
            "publishedAt": "2024-01-01T00:00:00Z",
            "resourceId": {"videoId": video_id},
        },
        "status": {"privacyStatus": privacy_status},
        "contentDetails": {
            "videoId": video_id,
            "videoPublishedAt": "2023-06-01T00:00:00Z",
        },
    }


@pytest.fixture
def fake_credential() -> SimpleNamespace:
    """A fake `GoogleOAuthCredential`-shaped object with ciphertext tokens."""
    return SimpleNamespace(
        access_token="ciphertext-access",
        refresh_token="ciphertext-refresh",
        scopes="https://www.googleapis.com/auth/youtube",
    )


@pytest.fixture
def mock_google_auth_service(fake_credential: SimpleNamespace) -> MagicMock:
    """A stand-in for GoogleAuthService — never touches Google's OAuth endpoints."""
    service = MagicMock()
    service.get_valid_credential.return_value = fake_credential
    service.repository.encryption.decrypt.side_effect = lambda value: f"decrypted:{value}"
    return service


@pytest.fixture
def playlist_repository(test_db: Session) -> PlaylistRepository:
    """A real PlaylistRepository over the in-memory test database."""
    return PlaylistRepository(test_db)


@pytest.fixture
def quota_service(test_db: Session) -> QuotaService:
    """A real QuotaService over the in-memory test database."""
    return QuotaService(QuotaRepository(test_db))


@pytest.fixture
def sync_service(
    playlist_repository: PlaylistRepository,
    mock_google_auth_service: MagicMock,
    quota_service: QuotaService,
) -> PlaylistSyncService:
    """A PlaylistSyncService wired to real repositories and a mocked Google auth."""
    return PlaylistSyncService(
        playlist_repository=playlist_repository,
        google_auth_service=mock_google_auth_service,
        quota_service=quota_service,
    )


def _mock_data_service(
    playlist_pages: list[list[dict]], items_by_playlist: dict[str, list[list[dict]]]
) -> MagicMock:
    """Build a MagicMock standing in for YouTubeDataService."""
    mock = MagicMock()
    mock.list_my_playlists.return_value = playlist_pages
    mock.list_playlist_items.side_effect = lambda playlist_id: items_by_playlist[playlist_id]
    return mock


class TestCredentialHandling:
    """The ciphertext invariant: decrypt into locals, never write back."""

    def test_builds_client_from_decrypted_tokens_without_mutating_credential(
        self,
        sync_service: PlaylistSyncService,
        mock_google_auth_service: MagicMock,
        fake_credential: SimpleNamespace,
    ) -> None:
        mock_data_service = _mock_data_service([[]], {})
        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ) as mock_class:
            sync_service.sync_owned_playlists("user-1")

        mock_google_auth_service.repository.encryption.decrypt.assert_any_call(
            "ciphertext-access"
        )
        mock_google_auth_service.repository.encryption.decrypt.assert_any_call(
            "ciphertext-refresh"
        )

        built_credentials = mock_class.call_args.args[0]
        assert built_credentials.token == "decrypted:ciphertext-access"
        assert built_credentials.refresh_token == "decrypted:ciphertext-refresh"

        # The ORM-shaped credential object itself must never be mutated.
        assert fake_credential.access_token == "ciphertext-access"
        assert fake_credential.refresh_token == "ciphertext-refresh"


class TestSyncOwnedPlaylists:
    """AC1a: a large paginated sync completes fast and logs quota correctly."""

    def test_5000_item_sync_completes_fast_and_logs_roughly_100_quota_units(
        self,
        sync_service: PlaylistSyncService,
        playlist_repository: PlaylistRepository,
        test_db: Session,
        test_user: User,
    ) -> None:
        total_items = 5000
        all_items = [
            _raw_item(f"IT{i}", _video_id(i)) for i in range(total_items)
        ]
        item_pages = [
            all_items[i : i + PAGE_SIZE] for i in range(0, len(all_items), PAGE_SIZE)
        ]
        playlist_pages = [[_raw_playlist("PL1", "Big Playlist", total_items)]]
        mock_data_service = _mock_data_service(
            playlist_pages, {"PL1": item_pages}
        )

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            start = time.perf_counter()
            result = sync_service.sync_owned_playlists(test_user.id)
            elapsed = time.perf_counter() - start

        assert elapsed < 60
        assert result.playlists_synced == 1
        assert result.items_synced == total_items
        assert result.quota_units_used == 101

        rows, total = sync_service.list_playlists(test_user.id, skip=0, limit=10)
        assert total == 1
        playlist, duplicate_count, unavailable_count = rows[0]
        assert playlist_repository.count_items(playlist.id) == total_items
        assert duplicate_count == 0
        assert unavailable_count == 0

        entries = test_db.query(QuotaLedgerEntry).all()
        # 1 page of playlists.list + 100 pages of playlistItems.list (5000 / 50).
        assert len(entries) == 101
        assert sum(entry.units for entry in entries) == 101
        assert all(entry.user_id == test_user.id for entry in entries)

    def test_resync_is_idempotent(
        self,
        sync_service: PlaylistSyncService,
        playlist_repository: PlaylistRepository,
        test_user: User,
    ) -> None:
        items = [_raw_item("IT1", _video_id(1)), _raw_item("IT2", _video_id(2))]
        playlist_pages = [[_raw_playlist("PL1", "My Playlist", 2)]]
        mock_data_service = _mock_data_service(playlist_pages, {"PL1": [items]})

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            sync_service.sync_owned_playlists(test_user.id)
            sync_service.sync_owned_playlists(test_user.id)

        assert playlist_repository.count(test_user.id) == 1
        playlist = playlist_repository.get_by_youtube_id(test_user.id, "PL1")
        assert playlist_repository.count_items(playlist.id) == 2


class TestComputeCounts:
    """AC4: a video appearing twice yields two distinct rows and a dupe count of 1."""

    def test_duplicate_video_produces_two_rows_and_duplicate_count_one(
        self,
        sync_service: PlaylistSyncService,
        playlist_repository: PlaylistRepository,
        test_user: User,
    ) -> None:
        dup_video_id = _video_id(1)
        items = [
            _raw_item("IT1", dup_video_id),
            _raw_item("IT2", dup_video_id),
            _raw_item("IT3", _video_id(2)),
        ]
        playlist_pages = [[_raw_playlist("PL1", "Dupe Playlist", 3)]]
        mock_data_service = _mock_data_service(playlist_pages, {"PL1": [items]})

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            sync_service.sync_owned_playlists(test_user.id)

        rows, _ = sync_service.list_playlists(test_user.id, skip=0, limit=10)
        playlist, duplicate_count, unavailable_count = rows[0]
        cached_items = playlist_repository.list_items(playlist.id, limit=10)
        matching = [item for item in cached_items if item.video_id == dup_video_id]
        assert len(matching) == 2
        assert len({item.id for item in matching}) == 2  # two distinct rows
        assert duplicate_count == 1
        assert unavailable_count == 0

        counts = sync_service.compute_counts(playlist.id)
        assert counts == {"duplicate_count": 1, "unavailable_count": 0}

    def test_unavailable_items_are_counted(
        self,
        sync_service: PlaylistSyncService,
        playlist_repository: PlaylistRepository,
        test_user: User,
    ) -> None:
        items = [
            _raw_item("IT1", _video_id(1), title="Deleted video", privacy_status="private"),
            _raw_item("IT2", _video_id(2), title="Private video", privacy_status="private"),
            _raw_item("IT3", _video_id(3)),
        ]
        playlist_pages = [[_raw_playlist("PL1", "Mixed Playlist", 3)]]
        mock_data_service = _mock_data_service(playlist_pages, {"PL1": [items]})

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            sync_service.sync_owned_playlists(test_user.id)

        rows, _ = sync_service.list_playlists(test_user.id, skip=0, limit=10)
        playlist, duplicate_count, unavailable_count = rows[0]
        assert duplicate_count == 0
        assert unavailable_count == 2

        counts = sync_service.compute_counts(playlist.id)
        assert counts == {"duplicate_count": 0, "unavailable_count": 2}


class TestGetPlaylistItems:
    """Ownership-scoped, paginated item reads for the router's GET /{id}/items."""

    def test_returns_items_and_total_for_owner(
        self,
        sync_service: PlaylistSyncService,
        test_user: User,
    ) -> None:
        items = [_raw_item("IT1", _video_id(1)), _raw_item("IT2", _video_id(2))]
        playlist_pages = [[_raw_playlist("PL1", "My Playlist", 2)]]
        mock_data_service = _mock_data_service(playlist_pages, {"PL1": [items]})

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            sync_service.sync_owned_playlists(test_user.id)

        rows, _ = sync_service.list_playlists(test_user.id, skip=0, limit=10)
        playlist = rows[0][0]

        result = sync_service.get_playlist_items(playlist.id, test_user.id, skip=0, limit=1)

        assert result is not None
        page_items, total = result
        assert total == 2
        assert len(page_items) == 1

    def test_returns_none_for_missing_playlist(
        self, sync_service: PlaylistSyncService, test_user: User
    ) -> None:
        assert sync_service.get_playlist_items("does-not-exist", test_user.id) is None

    def test_returns_none_when_not_owned_by_user(
        self,
        sync_service: PlaylistSyncService,
        test_user: User,
        test_admin: User,
    ) -> None:
        playlist_pages = [[_raw_playlist("PL1", "My Playlist", 0)]]
        mock_data_service = _mock_data_service(playlist_pages, {"PL1": [[]]})

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            sync_service.sync_owned_playlists(test_user.id)

        rows, _ = sync_service.list_playlists(test_user.id, skip=0, limit=10)
        playlist = rows[0][0]

        assert sync_service.get_playlist_items(playlist.id, test_admin.id) is None
