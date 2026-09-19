"""Tests for the dedupe & purge-unavailable plan-generation strategies
.

No test here ever reaches the network or spends real YouTube Data API
quota. `YouTubeDataService` is patched where `plan_apply_service` /
`playlist_planning_service` constructs it, matching the pattern established
in `tests/test_playlist_planning_service.py`. Google OAuth is always mocked
via a stand-in for `GoogleAuthService`.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.playlist import Playlist, PlaylistItem
from src.models.user import User
from src.repositories.google_oauth_repository import GoogleOAuthRepository
from src.repositories.plan_repository import PlanRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.quota_repository import QuotaRepository
from src.services.plan_apply_service import apply_plan
from src.services.playlist_planning_service import PlaylistPlanningService
from src.services.quota_service import QuotaService


def _seed_playlist(
    db: Session, user_id: str, youtube_playlist_id: str = "PL_TEST"
) -> Playlist:
    playlist = Playlist(
        id=str(uuid4()),
        user_id=user_id,
        youtube_playlist_id=youtube_playlist_id,
        title="Test Playlist",
        privacy_status="public",
        item_count=0,
        is_owned=True,
        last_synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def _seed_item(
    db: Session,
    playlist_id: str,
    *,
    youtube_playlist_item_id: str,
    video_id: str,
    position: int,
    title: str = "A Video",
    availability: str = "available",
) -> PlaylistItem:
    item = PlaylistItem(
        id=str(uuid4()),
        playlist_id=playlist_id,
        youtube_playlist_item_id=youtube_playlist_item_id,
        video_id=video_id,
        title=title,
        position=position,
        availability=availability,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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
        scopes="https://www.googleapis.com/auth/youtube",
    )


@pytest.fixture
def fake_credential() -> SimpleNamespace:
    """A fake GoogleOAuthCredential-shaped object with ciphertext tokens."""
    return SimpleNamespace(
        access_token="ciphertext-access",
        refresh_token="ciphertext-refresh",
        scopes="https://www.googleapis.com/auth/youtube",
    )


@pytest.fixture
def mock_google_auth_service(fake_credential: SimpleNamespace) -> MagicMock:
    """A stand-in `GoogleAuthService` -- no test needs it to touch real OAuth."""
    service = MagicMock()
    service.get_valid_credential.return_value = fake_credential
    service.repository.encryption.decrypt.side_effect = lambda value: f"decrypted:{value}"
    return service


def _make_service(
    test_db: Session, mock_google_auth_service: MagicMock
) -> PlaylistPlanningService:
    return PlaylistPlanningService(
        PlanRepository(test_db),
        PlaylistRepository(test_db),
        mock_google_auth_service,
        QuotaService(QuotaRepository(test_db)),
    )


class TestPlanDedupe:
    """AC1a: dedupe emits one delete op per duplicate, keep-first-seen."""

    def test_targets_second_occurrence_and_keeps_first(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        first = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_FIRST", video_id="vidAAAAAAAA",
            position=0, title="Original",
        )
        second = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_SECOND", video_id="vidAAAAAAAA",
            position=1, title="Duplicate",
        )

        with patch("src.services.youtube_data_service.build") as mock_build:
            service = _make_service(test_db, mock_google_auth_service)
            plan = service.plan_dedupe(user_id=test_user.id, playlist_id=playlist.id)

        assert mock_build.call_count == 0
        assert plan.kind == "dedupe"
        assert plan.status == "pending"

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].op_type == "delete_playlist_item"
        assert ops[0].payload == {"playlist_item_id": second.youtube_playlist_item_id}
        assert ops[0].estimated_units == 50
        assert first.youtube_playlist_item_id not in [
            op.payload["playlist_item_id"] for op in ops
        ]

        assert plan.params["playlist_id"] == playlist.id
        assert plan.params["removals"] == [
            {"sequence": 0, "video_id": "vidAAAAAAAA", "title": "Duplicate", "position": 1}
        ]

    def test_no_duplicates_produces_zero_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_2", video_id="vidBBBBBBBB", position=1,
        )

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_dedupe(user_id=test_user.id, playlist_id=playlist.id)

        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []
        assert plan.params["removals"] == []

    def test_returns_none_for_unknown_playlist(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_service(test_db, mock_google_auth_service)
        assert service.plan_dedupe(user_id=test_user.id, playlist_id=str(uuid4())) is None

    def test_does_not_dedupe_across_different_playlists(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist_a = _seed_playlist(test_db, test_user.id, "PL_A")
        playlist_b = _seed_playlist(test_db, test_user.id, "PL_B")
        _seed_item(
            test_db, playlist_a.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, playlist_b.id,
            youtube_playlist_item_id="B1", video_id="vidAAAAAAAA", position=0,
        )

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_dedupe(user_id=test_user.id, playlist_id=playlist_a.id)

        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []


class TestApplyDedupePlan:
    """AC1a: applying the dedupe plan invokes delete_playlist_item exactly
    once, against the duplicate item -- resuming never reinvokes it."""

    def test_apply_deletes_only_the_duplicate_and_is_resumable(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_FIRST", video_id="vidAAAAAAAA", position=0,
        )
        duplicate = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_SECOND", video_id="vidAAAAAAAA", position=1,
        )

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_dedupe(user_id=test_user.id, playlist_id=playlist.id)

        mock_data_service = MagicMock()
        mock_data_service.delete_playlist_item.return_value = {
            "playlist_item_id": duplicate.youtube_playlist_item_id,
            "deleted": True,
        }

        with patch(
            "src.services.plan_apply_service.get_google_auth_service",
            return_value=mock_google_auth_service,
        ), patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        mock_data_service.delete_playlist_item.assert_called_once_with(
            playlist_item_id=duplicate.youtube_playlist_item_id
        )

        plan_repository = PlanRepository(test_db)
        ops = plan_repository.get_ops_for_plan(plan.id)
        assert ops[0].status == "done"
        assert ops[0].actual_units == 50
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestPlanPurgeUnavailable:
    """AC2: conservative mode only targets "deleted"; aggressive mode
    additionally targets "private", verified via a dry-run diff."""

    def test_conservative_mode_targets_only_deleted(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="OK", video_id="vidOKOKOKOK", position=0,
            availability="available",
        )
        deleted = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="DEL", video_id="vidDELDELDE", position=1,
            title="Deleted video", availability="deleted",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PRIV", video_id="vidPRIVPRIV", position=2,
            title="Private video", availability="private",
        )

        with patch("src.services.youtube_data_service.build") as mock_build:
            service = _make_service(test_db, mock_google_auth_service)
            plan = service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="deleted"
            )

        assert mock_build.call_count == 0
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].payload == {"playlist_item_id": deleted.youtube_playlist_item_id}
        assert plan.params["mode"] == "deleted"
        assert plan.params["enrich"] is False

    def test_aggressive_mode_additionally_catches_private_items(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        available = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="OK", video_id="vidOKOKOKOK", position=0,
            availability="available",
        )
        deleted = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="DEL", video_id="vidDELDELDE", position=1,
            title="Deleted video", availability="deleted",
        )
        private = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PRIV", video_id="vidPRIVPRIV", position=2,
            title="Private video", availability="private",
        )

        # Aggressive mode forces enrichment -- the one remaining
        # "available" item is checked and resolves fine, so it must NOT
        # be added as an extra removal candidate.
        mock_data_service = MagicMock()
        mock_data_service.list_videos_batch.side_effect = lambda video_ids: iter(
            [{vid: {"id": vid, "status": {"uploadStatus": "processed"}} for vid in video_ids}]
        )

        with patch(
            "src.services.playlist_planning_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            service = _make_service(test_db, mock_google_auth_service)
            conservative_plan = service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="deleted"
            )
            aggressive_plan = service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="deleted_and_private"
            )

        mock_data_service.list_videos_batch.assert_called_once_with([available.video_id])

        conservative_ids = {
            op.payload["playlist_item_id"]
            for op in PlanRepository(test_db).get_ops_for_plan(conservative_plan.id)
        }
        aggressive_ids = {
            op.payload["playlist_item_id"]
            for op in PlanRepository(test_db).get_ops_for_plan(aggressive_plan.id)
        }

        assert conservative_ids == {deleted.youtube_playlist_item_id}
        assert aggressive_ids == {
            deleted.youtube_playlist_item_id, private.youtube_playlist_item_id,
        }
        # The dry-run diff: aggressive mode strictly adds the private item.
        assert aggressive_ids - conservative_ids == {private.youtube_playlist_item_id}
        assert aggressive_plan.params["mode"] == "deleted_and_private"
        assert aggressive_plan.params["enrich"] is True

    def test_enrich_opt_in_adds_unresolvable_item_in_conservative_mode(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        region_blocked = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="BLOCKED", video_id="vidBLOCKEDXX", position=0,
            availability="unknown",
        )

        mock_data_service = MagicMock()
        # videos.list returns nothing for this video_id -- unresolvable.
        mock_data_service.list_videos_batch.side_effect = lambda video_ids: iter([{}])

        with patch(
            "src.services.playlist_planning_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            service = _make_service(test_db, mock_google_auth_service)
            plan = service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="deleted", enrich=True
            )

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].payload == {
            "playlist_item_id": region_blocked.youtube_playlist_item_id
        }

    def test_invalid_mode_raises_value_error(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        service = _make_service(test_db, mock_google_auth_service)
        with pytest.raises(ValueError):
            service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="not-a-real-mode"
            )

    def test_returns_none_for_unknown_playlist(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_service(test_db, mock_google_auth_service)
        result = service.plan_purge_unavailable(
            user_id=test_user.id, playlist_id=str(uuid4())
        )
        assert result is None


class TestPurgeCostAndReads:
    """AC4: ~50 units per removed item, no reads beyond the optional
    enrichment pass, batched 1 quota unit per 50 IDs."""

    def test_estimated_units_are_fifty_per_removal(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        for i in range(3):
            _seed_item(
                test_db, playlist.id,
                youtube_playlist_item_id=f"DEL{i}", video_id=f"vidDEL{i:07d}",
                position=i, availability="deleted",
            )

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_purge_unavailable(
            user_id=test_user.id, playlist_id=playlist.id, mode="deleted"
        )

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 3
        assert all(op.estimated_units == 50 for op in ops)
        assert sum(op.estimated_units for op in ops) == 150

    def test_enrichment_records_one_quota_unit_per_batch(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        for i in range(3):
            _seed_item(
                test_db, playlist.id,
                youtube_playlist_item_id=f"OK{i}", video_id=f"vidOK{i:08d}",
                position=i, availability="available",
            )

        mock_data_service = MagicMock()
        # Two batches worth of enrichment reads, mirroring
        # `YouTubeDataService.list_videos_batch`'s per-VIDEOS_BATCH_SIZE
        # yield, all resolving fine (no extra removals).
        mock_data_service.list_videos_batch.side_effect = lambda video_ids: iter(
            [
                {vid: {"id": vid} for vid in video_ids[:2]},
                {vid: {"id": vid} for vid in video_ids[2:]},
            ]
        )

        quota_repository = QuotaRepository(test_db)
        with patch(
            "src.services.playlist_planning_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            service = PlaylistPlanningService(
                PlanRepository(test_db),
                PlaylistRepository(test_db),
                mock_google_auth_service,
                QuotaService(quota_repository),
            )
            service.plan_purge_unavailable(
                user_id=test_user.id, playlist_id=playlist.id, mode="deleted", enrich=True
            )

        units_used = quota_repository.get_units_used_since(
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        )
        assert units_used == 2  # 1 unit per batch, 2 batches


class TestPlansRouterDedupePurge:
    """Router-level dry-run checks (AC3): titles/positions surface in the
    plan response; no real API calls happen without enrichment."""

    def test_dedupe_dry_run_shows_title_and_position(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_FIRST", video_id="vidAAAAAAAA",
            position=0, title="Original",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PLI_SECOND", video_id="vidAAAAAAAA",
            position=1, title="Duplicate",
        )

        with patch("src.services.youtube_data_service.build") as mock_build:
            response = client.post(
                "/api/plans", json={"kind": "dedupe", "playlist_id": playlist.id}
            )

        assert mock_build.call_count == 0
        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "dedupe"
        assert body["params"]["removals"] == [
            {"sequence": 0, "video_id": "vidAAAAAAAA", "title": "Duplicate", "position": 1}
        ]
        assert len(body["ops"]) == 1
        assert body["ops"][0]["op_type"] == "delete_playlist_item"
        assert body["ops"][0]["estimated_units"] == 50

    def test_purge_conservative_dry_run_shows_title_and_position(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="DEL", video_id="vidDELDELDE",
            position=0, title="Deleted video", availability="deleted",
        )

        with patch("src.services.youtube_data_service.build") as mock_build:
            response = client.post(
                "/api/plans",
                json={"kind": "purge_unavailable", "playlist_id": playlist.id},
            )

        assert mock_build.call_count == 0
        assert response.status_code == 201
        body = response.json()
        assert body["params"]["mode"] == "deleted"
        assert body["params"]["removals"] == [
            {"sequence": 0, "video_id": "vidDELDELDE", "title": "Deleted video", "position": 0}
        ]

    def test_dedupe_unknown_playlist_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/plans", json={"kind": "dedupe", "playlist_id": str(uuid4())}
        )
        assert response.status_code == 404

    def test_purge_invalid_mode_returns_422(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        response = client.post(
            "/api/plans",
            json={
                "kind": "purge_unavailable",
                "playlist_id": playlist.id,
                "mode": "not-a-real-mode",
            },
        )
        assert response.status_code == 422

    def test_purge_aggressive_without_google_account_returns_400(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="OK", video_id="vidOKOKOKOK",
            position=0, availability="available",
        )

        response = client.post(
            "/api/plans",
            json={
                "kind": "purge_unavailable",
                "playlist_id": playlist.id,
                "mode": "deleted_and_private",
            },
        )
        assert response.status_code == 400

    def test_purge_aggressive_with_enrichment_via_router(
        self, client: TestClient, test_db: Session, test_user: User,
    ) -> None:
        _seed_google_credential(test_db, test_user.id)
        playlist = _seed_playlist(test_db, test_user.id)
        available = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="OK", video_id="vidOKOKOKOK",
            position=0, availability="available",
        )
        private = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="PRIV", video_id="vidPRIVPRIV",
            position=1, title="Private video", availability="private",
        )

        mock_data_service = MagicMock()
        mock_data_service.list_videos_batch.side_effect = lambda video_ids: iter(
            [{vid: {"id": vid} for vid in video_ids}]
        )

        with patch(
            "src.services.playlist_planning_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            response = client.post(
                "/api/plans",
                json={
                    "kind": "purge_unavailable",
                    "playlist_id": playlist.id,
                    "mode": "deleted_and_private",
                },
            )

        assert response.status_code == 201
        body = response.json()
        removed_ids = {r["video_id"] for r in body["params"]["removals"]}
        assert removed_ids == {private.video_id}
        assert available.video_id not in removed_ids
