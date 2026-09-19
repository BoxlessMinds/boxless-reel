"""Integration tests for the playlist sync & library view router.

Exercises the real router -> service -> repository -> DB chain. The only
external boundary mocked is `YouTubeDataService` (patched where
`PlaylistSyncService` constructs it) — no test here reaches the network or
spends live YouTube Data API quota.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.config import settings
from src.models.playlist import Playlist, PlaylistItem, QuotaLedgerEntry
from src.models.user import User
from src.repositories.google_oauth_repository import GoogleOAuthRepository
from src.repositories.playlist_repository import PlaylistRepository


def _seed_google_credential(test_db: Session, user_id: str) -> None:
    """Seed a non-expired Google OAuth credential so `get_valid_credential`
    returns immediately without attempting a token refresh."""
    GoogleOAuthRepository(test_db).upsert(
        user_id=user_id,
        google_account_email="test@example.com",
        google_account_id="google-sub-123",
        access_token="plaintext-access-token",
        refresh_token="plaintext-refresh-token",
        token_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        scopes="https://www.googleapis.com/auth/youtube.readonly",
    )


def _raw_playlist(youtube_playlist_id: str, *, item_count: int) -> dict[str, Any]:
    return {
        "id": youtube_playlist_id,
        "snippet": {"title": "My Playlist", "description": "A test playlist"},
        "status": {"privacyStatus": "public"},
        "contentDetails": {"itemCount": item_count},
    }


def _raw_item(youtube_playlist_item_id: str, video_id: str, position: int) -> dict[str, Any]:
    return {
        "id": youtube_playlist_item_id,
        "snippet": {
            "title": f"Video {video_id}",
            "channelTitle": "Test Channel",
            "position": position,
            "publishedAt": "2024-01-01T00:00:00Z",
        },
        "status": {"privacyStatus": "public"},
        "contentDetails": {"videoId": video_id, "videoPublishedAt": "2024-01-01T00:00:00Z"},
    }


@pytest.fixture
def mock_youtube_data_service() -> MagicMock:
    """A fake `YouTubeDataService` yielding one playlist with two items.

    Uses `side_effect` (not `return_value`) so each call gets a fresh
    generator — a re-sync must see the same fixture data again, not an
    already-exhausted iterator from the first call.
    """
    instance = MagicMock()
    instance.list_my_playlists.side_effect = lambda: iter(
        [[_raw_playlist("PL_TEST_1", item_count=2)]]
    )
    instance.list_playlist_items.side_effect = lambda playlist_id: iter(
        [[_raw_item("PLI_1", "vid00000001", 0), _raw_item("PLI_2", "vid00000002", 1)]]
    )
    return instance


class TestSyncEndpoint:
    """AC3: re-running POST /sync twice produces no duplicate rows; existing
    rows are updated in place."""

    def test_resync_is_idempotent(
        self, client: TestClient, test_db: Session, test_user: User,
        mock_youtube_data_service: MagicMock,
    ) -> None:
        _seed_google_credential(test_db, test_user.id)

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_youtube_data_service,
        ):
            first = client.post("/api/playlists/sync")
            second = client.post("/api/playlists/sync")

        assert first.status_code == 200
        assert second.status_code == 200

        for body in (first.json(), second.json()):
            assert body["playlists_synced"] == 1
            assert body["items_synced"] == 2
            assert body["quota_units_used"] == 2
            assert body["synced_at"]

        repository = PlaylistRepository(test_db)
        playlist = repository.get_by_youtube_id(test_user.id, "PL_TEST_1")
        assert playlist is not None
        assert repository.count(test_user.id) == 1
        assert repository.count_items(playlist.id) == 2

    def test_sync_without_connected_google_account_returns_400(
        self, client: TestClient,
    ) -> None:
        response = client.post("/api/playlists/sync")
        assert response.status_code == 400


class TestListPlaylistsEndpoint:
    """AC2a: GET "" returns item/dupe/unavailable counts matching a
    fixture-seeded playlist."""

    def test_list_returns_accurate_counts(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = Playlist(
            id=str(uuid4()),
            user_id=test_user.id,
            youtube_playlist_id="PL_FIXTURE",
            title="Fixture Playlist",
            description=None,
            privacy_status="public",
            item_count=3,
            is_owned=True,
            last_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        test_db.add(playlist)
        test_db.commit()
        test_db.refresh(playlist)

        # video A appears twice (duplicate); video B is private (unavailable).
        items = [
            PlaylistItem(
                id=str(uuid4()), playlist_id=playlist.id,
                youtube_playlist_item_id="PLI_A1", video_id="videoAAAAAA",
                position=0, availability="available",
            ),
            PlaylistItem(
                id=str(uuid4()), playlist_id=playlist.id,
                youtube_playlist_item_id="PLI_A2", video_id="videoAAAAAA",
                position=1, availability="available",
            ),
            PlaylistItem(
                id=str(uuid4()), playlist_id=playlist.id,
                youtube_playlist_item_id="PLI_B1", video_id="videoBBBBBB",
                position=2, availability="private",
            ),
        ]
        for item in items:
            test_db.add(item)
        test_db.commit()

        response = client.get("/api/playlists")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

        result = body["items"][0]
        assert result["youtube_playlist_id"] == "PL_FIXTURE"
        assert result["item_count"] == 3
        assert result["duplicate_count"] == 1
        assert result["unavailable_count"] == 1

    def test_list_is_scoped_to_current_user(
        self, client: TestClient, test_db: Session,
    ) -> None:
        other_user = User(
            id=str(uuid4()), email="other@example.com", display_name="Other",
            password_hash="x", role="user", is_active=True,
        )
        test_db.add(other_user)
        test_db.commit()

        other_playlist = Playlist(
            id=str(uuid4()), user_id=other_user.id,
            youtube_playlist_id="PL_OTHER", title="Not Mine",
            privacy_status="public", item_count=0, is_owned=True,
            last_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        test_db.add(other_playlist)
        test_db.commit()

        response = client.get("/api/playlists")

        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestPlaylistItemsEndpoint:
    """GET /{id}/items — paginated item list, ownership-checked."""

    def test_returns_items_for_owned_playlist(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = Playlist(
            id=str(uuid4()), user_id=test_user.id,
            youtube_playlist_id="PL_ITEMS", title="Has Items",
            privacy_status="public", item_count=1, is_owned=True,
            last_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        test_db.add(playlist)
        test_db.commit()
        test_db.refresh(playlist)

        item = PlaylistItem(
            id=str(uuid4()), playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_ONLY", video_id="videoCCCCCC",
            title="Video C", position=0, availability="available",
        )
        test_db.add(item)
        test_db.commit()

        response = client.get(f"/api/playlists/{playlist.id}/items")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["video_id"] == "videoCCCCCC"

    def test_returns_404_for_unknown_playlist(self, client: TestClient) -> None:
        response = client.get(f"/api/playlists/{uuid4()}/items")
        assert response.status_code == 404


class TestCreatePlanEndpoint:
    """AC3: POST /api/plans (kind="create") + GET /api/plans/{id} -- dry-run
    preview shows title/description/privacy before anything is created."""

    def test_create_plan_then_get_shows_pending_payload(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "create",
                "title": "My New Playlist",
                "description": "A test description",
                "privacy_status": "private",
            },
        )

        assert response.status_code == 201
        created = response.json()
        assert created["status"] == "pending"
        assert created["kind"] == "create"
        assert len(created["ops"]) == 1
        assert created["ops"][0]["op_type"] == "insert_playlist"
        assert created["ops"][0]["status"] == "pending"
        assert created["ops"][0]["payload"] == {
            "title": "My New Playlist",
            "description": "A test description",
            "privacy_status": "private",
        }

        plan_id = created["id"]
        get_response = client.get(f"/api/plans/{plan_id}")

        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["status"] == "pending"
        assert fetched["ops"][0]["payload"] == {
            "title": "My New Playlist",
            "description": "A test description",
            "privacy_status": "private",
        }


def _seed_playlist_for_copy(
    db: Session, user_id: str, youtube_playlist_id: str, title: str = "Test Playlist"
) -> Playlist:
    playlist = Playlist(
        id=str(uuid4()),
        user_id=user_id,
        youtube_playlist_id=youtube_playlist_id,
        title=title,
        privacy_status="public",
        item_count=0,
        is_owned=True,
        last_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def _seed_item_for_copy(
    db: Session, playlist_id: str, *, youtube_playlist_item_id: str, video_id: str, position: int
) -> PlaylistItem:
    item = PlaylistItem(
        id=str(uuid4()),
        playlist_id=playlist_id,
        youtube_playlist_item_id=youtube_playlist_item_id,
        video_id=video_id,
        title="A Video",
        position=position,
        availability="available",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


class TestCreateCopyPlanEndpoint:
    """POST /api/plans (kind="copy") -- schema validation, dispatch, and
    dry-run response shape end-to-end through the real router/service/
    repository chain."""

    def test_copy_plan_dry_run_shows_ops_and_empty_warnings(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        source = _seed_playlist_for_copy(test_db, test_user.id, "PL_A")
        _seed_item_for_copy(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )

        response = client.post(
            "/api/plans",
            json={
                "kind": "copy",
                "source_playlist_ids": ["PL_A"],
                "target_playlist_id": None,
                "target_title": "My New Mix",
                "filter_regex": None,
                "force_new": False,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "copy"
        assert body["params"]["warnings"] == []
        assert [op["op_type"] for op in body["ops"]] == [
            "insert_playlist", "insert_playlist_item",
        ]
        assert body["ops"][0]["estimated_units"] == 50

    def test_copy_requires_exactly_one_target_returns_422(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "copy",
                "source_playlist_ids": ["PL_A"],
                "target_playlist_id": "some-id",
                "target_title": "Also set",
            },
        )
        assert response.status_code == 422

    def test_copy_empty_sources_returns_422(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "copy",
                "source_playlist_ids": [],
                "target_title": "My New Mix",
            },
        )
        assert response.status_code == 422

    def test_copy_invalid_filter_regex_returns_422(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "copy",
                "source_playlist_ids": ["PL_A"],
                "target_title": "My New Mix",
                "filter_regex": "[unterminated",
            },
        )
        assert response.status_code == 422

    def test_copy_unknown_target_playlist_id_returns_404(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        source = _seed_playlist_for_copy(test_db, test_user.id, "PL_A")
        _seed_item_for_copy(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )

        response = client.post(
            "/api/plans",
            json={
                "kind": "copy",
                "source_playlist_ids": ["PL_A"],
                "target_playlist_id": str(uuid4()),
            },
        )
        assert response.status_code == 404


class TestCreateMovePlanEndpoint:
    """POST /api/plans (kind="move") -- schema validation, dispatch, and
    dry-run response shape end-to-end through the real router/service/
    repository chain."""

    def test_move_plan_dry_run_shows_paired_ops(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        source = _seed_playlist_for_copy(test_db, test_user.id, "PL_SOURCE")
        target = _seed_playlist_for_copy(test_db, test_user.id, "PL_TARGET", title="Target")
        _seed_item_for_copy(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )

        response = client.post(
            "/api/plans",
            json={
                "kind": "move",
                "source_playlist_id": source.id,
                "target_playlist_id": target.id,
                "filter_regex": None,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "move"
        assert [op["op_type"] for op in body["ops"]] == [
            "insert_playlist_item", "delete_playlist_item",
        ]
        assert body["ops"][0]["sequence"] == 0
        assert body["ops"][1]["sequence"] == 1
        assert body["ops"][1]["depends_on_sequence"] == 0

    def test_move_unknown_playlist_returns_404(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "move",
                "source_playlist_id": str(uuid4()),
                "target_playlist_id": str(uuid4()),
                "filter_regex": None,
            },
        )
        assert response.status_code == 404


class TestCreateReorderPlanEndpoint:
    """POST /api/plans (kind="reorder") -- schema validation, dispatch, and
    dry-run response shape end-to-end through the real router/service/
    repository chain."""

    def test_reorder_plan_dry_run_shows_position_updates(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist_for_copy(test_db, test_user.id, "PL_REORDER")
        # Seeded in reverse title order (position 0 = "Zeta", position 1 =
        # "Alpha") so sorting by title yields exactly one displaced item.
        item_z = _seed_item_for_copy(
            test_db, playlist.id,
            youtube_playlist_item_id="Z1", video_id="vidZZZZZZZZ", position=0,
        )
        item_z.title = "Zeta Video"
        item_a = _seed_item_for_copy(
            test_db, playlist.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=1,
        )
        item_a.title = "Alpha Video"
        test_db.commit()

        response = client.post(
            "/api/plans",
            json={
                "kind": "reorder",
                "playlist_id": playlist.id,
                "sort_by": "title",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "reorder"
        # Swapping the two items means both are displaced from their
        # original position, so both get an update op.
        assert [op["op_type"] for op in body["ops"]] == [
            "update_playlist_item_position", "update_playlist_item_position",
        ]
        assert body["ops"][0]["estimated_units"] == 50

    def test_reorder_already_sorted_returns_zero_ops(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist_for_copy(test_db, test_user.id, "PL_SORTED")
        item_a = _seed_item_for_copy(
            test_db, playlist.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        item_a.title = "Alpha Video"
        item_z = _seed_item_for_copy(
            test_db, playlist.id,
            youtube_playlist_item_id="Z1", video_id="vidZZZZZZZZ", position=1,
        )
        item_z.title = "Zeta Video"
        test_db.commit()

        response = client.post(
            "/api/plans",
            json={
                "kind": "reorder",
                "playlist_id": playlist.id,
                "sort_by": "title",
            },
        )

        assert response.status_code == 201
        assert response.json()["ops"] == []

    def test_reorder_unknown_playlist_returns_404(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        response = client.post(
            "/api/plans",
            json={
                "kind": "reorder",
                "playlist_id": str(uuid4()),
                "sort_by": "title",
            },
        )
        assert response.status_code == 404


class TestQuotaEndpoint:
    """AC5: GET /api/playlists/quota reflects the shared global pool, summed
    across all users for the current Pacific day — not a per-user allowance
    and not a UTC-day window."""

    def test_quota_sums_all_users_within_todays_pacific_window(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        other_user = User(
            id=str(uuid4()), email="quota-other@example.com", display_name="Other",
            password_hash="x", role="user", is_active=True,
        )
        test_db.add(other_user)
        test_db.commit()

        pacific_midnight_today = datetime.now(ZoneInfo("America/Los_Angeles")).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        window_start_utc = pacific_midnight_today.astimezone(timezone.utc).replace(tzinfo=None)

        entries = [
            # Inside today's Pacific window, attributed to test_user.
            QuotaLedgerEntry(
                id=str(uuid4()), user_id=test_user.id, endpoint="playlists.list",
                units=300, created_at=window_start_utc + timedelta(hours=1),
            ),
            # Inside today's Pacific window, attributed to a DIFFERENT user —
            # a per-user sum would miss this and undercount usage.
            QuotaLedgerEntry(
                id=str(uuid4()), user_id=other_user.id, endpoint="playlistItems.list",
                units=150, created_at=window_start_utc + timedelta(hours=2),
            ),
            # Outside today's Pacific window (yesterday, Pacific time) — must
            # NOT be counted. A UTC-day window would wrongly include this
            # near the UTC/Pacific offset boundary.
            QuotaLedgerEntry(
                id=str(uuid4()), user_id=test_user.id, endpoint="playlists.list",
                units=9999, created_at=window_start_utc - timedelta(hours=1),
            ),
        ]
        for entry in entries:
            test_db.add(entry)
        test_db.commit()

        response = client.get("/api/playlists/quota")

        assert response.status_code == 200
        body = response.json()
        expected_used = 300 + 150
        assert body["daily_limit"] == settings.youtube_daily_quota_limit
        assert body["used"] == expected_used
        assert body["remaining"] == settings.youtube_daily_quota_limit - expected_used
