"""Tests for the move & reorder plan-generation strategies.

No test here ever reaches the network or spends real YouTube Data API
quota. `YouTubeDataService` is patched where `plan_apply_service`
constructs it, matching the pattern established in
`tests/test_playlist_planning_service.py`. Google OAuth is always mocked
via a stand-in for `GoogleAuthService`.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
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


def _seed_google_credential(test_db: Session, user_id: str) -> None:
    """Seed a non-expired Google OAuth credential so `apply_plan`'s own
    `_build_data_service` (which reads the DB directly, independent of any
    `google_auth_service` mock passed to `PlaylistPlanningService`) can
    resolve one without attempting a token refresh."""
    GoogleOAuthRepository(test_db).upsert(
        user_id=user_id,
        google_account_email="test@example.com",
        google_account_id="google-sub-123",
        access_token="plaintext-access-token",
        refresh_token="plaintext-refresh-token",
        token_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        scopes="https://www.googleapis.com/auth/youtube",
    )


def _seed_playlist(
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


def _seed_item(
    db: Session,
    playlist_id: str,
    *,
    youtube_playlist_item_id: str,
    video_id: str,
    position: int,
    title: str | None = "A Video",
    channel_title: str | None = None,
    published_at: datetime | None = None,
    added_at: datetime | None = None,
) -> PlaylistItem:
    item = PlaylistItem(
        id=str(uuid4()),
        playlist_id=playlist_id,
        youtube_playlist_item_id=youtube_playlist_item_id,
        video_id=video_id,
        title=title,
        channel_title=channel_title,
        position=position,
        availability="available",
        published_at=published_at,
        added_at=added_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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


class TestPlanMove:
    """Scope bullet 1: plan_move emits one insert+delete pair per deduped,
    filter-matched video."""

    def test_move_emits_paired_insert_delete_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0, title="Keep Me",
        )
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S2", video_id="vidBBBBBBBB", position=1, title="Skip Me",
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_move(
            user_id=test_user.id,
            source_playlist_id=source.id,
            target_playlist_id=target.id,
            filter_regex="Keep",
        )

        assert plan is not None
        assert plan.kind == "move"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == [
            "insert_playlist_item", "delete_playlist_item",
        ]
        assert ops[0].sequence == 0
        assert ops[0].payload == {"playlist_id": "PL_TARGET", "video_id": "vidAAAAAAAA"}
        assert ops[0].depends_on_sequence is None
        assert ops[1].sequence == 1
        assert ops[1].payload == {"playlist_item_id": "S1"}
        assert ops[1].depends_on_sequence == 0
        assert len(plan.params["moves"]) == 1
        assert plan.params["moves"][0]["video_id"] == "vidAAAAAAAA"

    def test_move_dedupes_matched_items_by_video_id_first_seen(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S2", video_id="vidAAAAAAAA", position=1,
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_move(
            user_id=test_user.id, source_playlist_id=source.id, target_playlist_id=target.id,
        )

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 2
        assert ops[1].payload == {"playlist_item_id": "S1"}

    def test_move_source_equals_target_raises(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        service = _make_service(test_db, mock_google_auth_service)
        with pytest.raises(ValueError):
            service.plan_move(
                user_id=test_user.id, source_playlist_id=source.id, target_playlist_id=source.id,
            )

    def test_move_missing_source_or_target_returns_none(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        service = _make_service(test_db, mock_google_auth_service)

        assert service.plan_move(
            user_id=test_user.id, source_playlist_id="does-not-exist", target_playlist_id=target.id,
        ) is None
        assert service.plan_move(
            user_id=test_user.id, source_playlist_id=target.id, target_playlist_id="does-not-exist",
        ) is None

    def test_move_no_matches_produces_zero_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0, title="Nothing",
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_move(
            user_id=test_user.id, source_playlist_id=source.id, target_playlist_id=target.id,
            filter_regex="NoMatch",
        )

        assert plan is not None
        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []


class TestPlanMoveApplySemantics:
    """AC1/AC2: the insert+delete pairing, run through the real apply
    executor, never loses/duplicates a video and never deletes from the
    source unless the insert into the target is confirmed done."""

    def test_delete_only_runs_after_insert_is_done_and_survives_resume(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0,
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        _seed_google_credential(test_db, test_user.id)
        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_move(
            user_id=test_user.id, source_playlist_id=source.id, target_playlist_id=target.id,
        )
        assert plan is not None

        mock_data_service = MagicMock()
        mock_data_service.insert_playlist_item.return_value = {
            "youtube_playlist_item_id": "T1", "playlist_id": "PL_TARGET",
            "video_id": "vidAAAAAAAA", "position": 0,
        }
        mock_data_service.delete_playlist_item.return_value = {
            "playlist_item_id": "S1", "deleted": True,
        }

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            # Budget covers only the insert -- the executor halts before the
            # paired delete, simulating an interruption between the two ops.
            apply_plan(plan.id, test_user.id, budget_units=50, db=test_db)

            ops_mid_run = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
            assert ops_mid_run[0].status == "done"
            assert ops_mid_run[1].status == "pending"
            mock_data_service.delete_playlist_item.assert_not_called()

            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        assert mock_data_service.insert_playlist_item.call_count == 1
        assert mock_data_service.delete_playlist_item.call_count == 1
        final_ops = plan_repository.get_ops_for_plan(plan.id)
        assert all(op.status == "done" for op in final_ops)

    def test_failed_insert_causes_paired_delete_to_be_skipped_not_executed(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        from src.services.youtube_data_service import PermanentAPIError

        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0,
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        _seed_google_credential(test_db, test_user.id)
        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_move(
            user_id=test_user.id, source_playlist_id=source.id, target_playlist_id=target.id,
        )
        assert plan is not None

        mock_data_service = MagicMock()
        mock_data_service.insert_playlist_item.side_effect = PermanentAPIError("video unavailable")

        plan_repository = PlanRepository(test_db)
        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        # A PermanentAPIError marks the failing op "skipped" (not "failed")
        # and the executor keeps going rather than halting -- see
        # plan_apply_service.apply_plan's PermanentAPIError branch -- so the
        # paired delete observes a "skipped" dependency in the same run and
        # is itself skipped too, never invoked.
        assert ops[0].status == "skipped"
        assert ops[1].status == "skipped"
        mock_data_service.delete_playlist_item.assert_not_called()


class TestPlanReorder:
    """Scope bullet 3 / AC3-AC4: diff-only reorder, zero ops when
    already sorted, updates only for displaced items otherwise."""

    def test_already_sorted_playlist_produces_zero_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I1", video_id="v1", position=0, title="Alpha")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I2", video_id="v2", position=1, title="Bravo")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I3", video_id="v3", position=2, title="Charlie")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="title")

        assert plan is not None
        assert plan.kind == "reorder"
        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []
        assert plan.params["reorders"] == []

    def test_shuffled_playlist_emits_updates_only_for_displaced_items(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        # Already in title order except v2/v3 are swapped.
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I1", video_id="v1", position=0, title="Alpha")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I2", video_id="v3", position=1, title="Charlie")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I3", video_id="v2", position=2, title="Bravo")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="title")

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 2
        assert all(op.op_type == "update_playlist_item_position" for op in ops)
        payloads = {op.payload["video_id"]: op.payload for op in ops}
        assert payloads["v3"] == {
            "playlist_item_id": "I2", "playlist_id": "PL_A", "video_id": "v3", "position": 2,
        }
        assert payloads["v2"] == {
            "playlist_item_id": "I3", "playlist_id": "PL_A", "video_id": "v2", "position": 1,
        }

    def test_sort_by_title_is_case_insensitive(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I1", video_id="v1", position=0, title="bravo")
        _seed_item(test_db, playlist.id, youtube_playlist_item_id="I2", video_id="v2", position=1, title="Alpha")

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="title")

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 2
        by_video = {op.payload["video_id"]: op.payload["position"] for op in ops}
        assert by_video["v2"] == 0
        assert by_video["v1"] == 1

    def test_items_missing_sort_value_sort_last(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, playlist.id, youtube_playlist_item_id="I1", video_id="v1", position=0,
            published_at=None,
        )
        _seed_item(
            test_db, playlist.id, youtube_playlist_item_id="I2", video_id="v2", position=1,
            published_at=datetime(2024, 1, 1),
        )

        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="published")

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 2
        by_video = {op.payload["video_id"]: op.payload["position"] for op in ops}
        assert by_video["v2"] == 0
        assert by_video["v1"] == 1

    def test_sort_by_channel_and_added(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, playlist.id, youtube_playlist_item_id="I1", video_id="v1", position=0,
            channel_title="Zeta Channel", added_at=datetime(2024, 6, 1),
        )
        _seed_item(
            test_db, playlist.id, youtube_playlist_item_id="I2", video_id="v2", position=1,
            channel_title="Alpha Channel", added_at=datetime(2024, 1, 1),
        )

        service = _make_service(test_db, mock_google_auth_service)

        channel_plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="channel")
        assert channel_plan is not None
        channel_ops = PlanRepository(test_db).get_ops_for_plan(channel_plan.id)
        by_video = {op.payload["video_id"]: op.payload["position"] for op in channel_ops}
        assert by_video["v2"] == 0
        assert by_video["v1"] == 1

        added_plan = service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="added")
        assert added_plan is not None
        added_ops = PlanRepository(test_db).get_ops_for_plan(added_plan.id)
        by_video = {op.payload["video_id"]: op.payload["position"] for op in added_ops}
        assert by_video["v2"] == 0
        assert by_video["v1"] == 1

    def test_invalid_sort_by_raises(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_A")
        service = _make_service(test_db, mock_google_auth_service)
        with pytest.raises(ValueError):
            service.plan_reorder(user_id=test_user.id, playlist_id=playlist.id, sort_by="bogus")

    def test_missing_playlist_returns_none(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_service(test_db, mock_google_auth_service)
        plan = service.plan_reorder(user_id=test_user.id, playlist_id="does-not-exist", sort_by="title")
        assert plan is None
