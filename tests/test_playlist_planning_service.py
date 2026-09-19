"""Tests for the "create" and "copy"
plan-generation strategies.

No test here ever reaches the network or spends real YouTube Data API
quota. `YouTubeDataService` is patched at both construction points a copy
plan can exercise: `src.services.plan_apply_service.YouTubeDataService`
(apply-time) and `src.services.playlist_sync_service.YouTubeDataService`
(on-demand source caching, at plan-generation time). Google OAuth is always
mocked via a stand-in for `GoogleAuthService`.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.models.plan import PlanOp
from src.models.playlist import Playlist, PlaylistItem
from src.models.user import User
from src.repositories.plan_repository import PlanRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.quota_repository import QuotaRepository
from src.services.exceptions import InvalidVideoIdError
from src.services.plan_apply_service import apply_plan
from src.services.playlist_planning_service import PlaylistPlanningService
from src.services.quota_service import QuotaService


def _make_op(
    db: Session,
    plan_id: str,
    sequence: int,
    op_type: str,
    payload: dict | None = None,
) -> PlanOp:
    """Persist a bare PlanOp row directly onto an existing plan."""
    op = PlanOp(plan_id=plan_id, sequence=sequence, op_type=op_type, payload=payload)
    return PlanRepository(db).create_ops([op])[0]


def _make_planning_service(db: Session) -> PlaylistPlanningService:
    """Build a PlaylistPlanningService for the "create" strategy tests below.

    `plan_create` never touches `playlist_repository`/`google_auth_service`/
    `quota_service` (those back the dedupe/purge strategies), so bare
    `MagicMock()` stand-ins are enough here.
    """
    return PlaylistPlanningService(
        PlanRepository(db), PlaylistRepository(db), MagicMock(), MagicMock()
    )


def _make_copy_planning_service(
    db: Session, google_auth_service: MagicMock | None = None
) -> PlaylistPlanningService:
    """Build a PlaylistPlanningService for the "copy" strategy tests below.

    Uses a real `PlaylistRepository`/`QuotaService` (needed for
    `plan_copy`'s cache reads/dedupe and, in the on-demand-source test, real
    quota-ledger writes). `google_auth_service` only matters when a test
    exercises the on-demand source-caching path (a bare `MagicMock()` is
    fine otherwise, since it's never touched when every source is already
    cached).
    """
    return PlaylistPlanningService(
        PlanRepository(db),
        PlaylistRepository(db),
        google_auth_service or MagicMock(),
        QuotaService(QuotaRepository(db)),
    )


def _seed_playlist(
    db: Session,
    user_id: str,
    youtube_playlist_id: str,
    title: str = "Test Playlist",
    is_owned: bool = True,
) -> Playlist:
    """Persist a bare cached Playlist row directly (no API call)."""
    playlist = Playlist(
        id=str(uuid4()),
        user_id=user_id,
        youtube_playlist_id=youtube_playlist_id,
        title=title,
        privacy_status="public",
        item_count=0,
        is_owned=is_owned,
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
    channel_title: str | None = None,
    published_at: datetime | None = None,
    added_at: datetime | None = None,
) -> PlaylistItem:
    """Persist a bare cached PlaylistItem row directly (no API call).

    `channel_title`/`published_at`/`added_at` default to None (matching
    every earlier test's items) and only matter to `plan_reorder`
    tests exercising the "channel"/"published"/"added" `sort_by` options.
    """
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
def mock_google_auth_service(fake_credential: SimpleNamespace):
    """Patch `get_google_auth_service` so no test touches real Google OAuth."""
    service = MagicMock()
    service.get_valid_credential.return_value = fake_credential
    service.repository.encryption.decrypt.side_effect = lambda value: f"decrypted:{value}"
    with patch(
        "src.services.plan_apply_service.get_google_auth_service", return_value=service
    ):
        yield service


class TestPlanCreationIsFree:
    """`plan_create` never touches the API or the quota ledger."""

    def test_plan_create_is_free_and_pending(
        self, test_db: Session, test_user: User
    ) -> None:
        with patch("src.services.youtube_data_service.build") as mock_build:
            service = _make_planning_service(test_db)
            plan = service.plan_create(
                user_id=test_user.id,
                title="My Playlist",
                description="A description",
                privacy_status="private",
            )

        assert mock_build.call_count == 0
        assert plan.status == "pending"
        assert plan.kind == "create"

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].op_type == "insert_playlist"
        assert ops[0].sequence == 0
        assert ops[0].payload == {
            "title": "My Playlist",
            "description": "A description",
            "privacy_status": "private",
        }
        assert ops[0].status == "pending"


class TestResume:
    """AC1: an interrupted apply on the create plan never re-invokes insert_playlist."""

    def test_second_apply_does_not_reinvoke_insert_playlist(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_planning_service(test_db)
        plan = service.plan_create(
            user_id=test_user.id,
            title="My Playlist",
            description=None,
            privacy_status="private",
        )

        mock_data_service = MagicMock()
        mock_data_service.insert_playlist.return_value = {
            "youtube_playlist_id": "PL_NEW_123",
            "title": "My Playlist",
            "description": None,
            "privacy_status": "private",
        }

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        assert mock_data_service.insert_playlist.call_count == 1

        plan_repository = PlanRepository(test_db)
        ops = plan_repository.get_ops_for_plan(plan.id)
        assert ops[0].status == "done"
        assert ops[0].result == {
            "youtube_playlist_id": "PL_NEW_123",
            "title": "My Playlist",
            "description": None,
            "privacy_status": "private",
        }
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestRefResolution:
    """AC2: op0's persisted youtube_playlist_id resolves via a {"kind":"ref",...} in op1."""

    def test_ref_resolution_carries_created_playlist_id_into_dependent_op(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_planning_service(test_db)
        plan = service.plan_create(
            user_id=test_user.id,
            title="My Playlist",
            description=None,
            privacy_status="private",
        )
        # op1 stands in for a not-yet-built future strategy (e.g. a copy/build
        # feature) that would target the just-created playlist --
        # any synthetic op_type is fine here.
        _make_op(
            test_db, plan.id, sequence=1, op_type="consume",
            payload={"target": {"kind": "ref", "ref_sequence": 0}},
        )

        mock_data_service = MagicMock()
        mock_data_service.insert_playlist.return_value = {
            "youtube_playlist_id": "PL_NEW_456",
            "title": "My Playlist",
            "description": None,
            "privacy_status": "private",
        }
        mock_data_service.consume.return_value = {"ok": True}

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        mock_data_service.consume.assert_called_once_with(
            target={
                "youtube_playlist_id": "PL_NEW_456",
                "title": "My Playlist",
                "description": None,
                "privacy_status": "private",
            }
        )

        plan_repository = PlanRepository(test_db)
        ops = {op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)}
        assert ops[0].status == "done"
        assert ops[1].status == "done"
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestPlanCopy:
    """AC1: union of two sources, deduped, applied with no source mutation."""

    def test_union_dedupe_and_apply_copies_only_deduped_items(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source_a = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, source_a.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0, title="Song A1",
        )
        _seed_item(
            test_db, source_a.id,
            youtube_playlist_item_id="A2", video_id="vidBBBBBBBB", position=1, title="Song A2",
        )
        source_b = _seed_playlist(test_db, test_user.id, "PL_B")
        _seed_item(
            test_db, source_b.id,
            youtube_playlist_item_id="B1", video_id="vidBBBBBBBB", position=0, title="Song B1 dup",
        )
        _seed_item(
            test_db, source_b.id,
            youtube_playlist_item_id="B2", video_id="vidCCCCCCCC", position=1, title="Song B2",
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_copy(
            user_id=test_user.id,
            source_playlist_ids=["PL_A", "PL_B"],
            target_title="My Mix",
        )

        assert plan is not None
        assert plan.kind == "copy"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == [
            "insert_playlist", "insert_playlist_item", "insert_playlist_item",
            "insert_playlist_item",
        ]
        assert plan.params["warnings"] == []

        mock_data_service = MagicMock()
        mock_data_service.insert_playlist.return_value = {
            "youtube_playlist_id": "PL_NEW_1", "title": "My Mix",
            "description": None, "privacy_status": "private",
        }
        mock_data_service.insert_playlist_item.return_value = {
            "youtube_playlist_item_id": "PLI_NEW", "playlist_id": "PL_NEW_1",
            "video_id": "unused", "position": 0,
        }

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        mock_data_service.delete_playlist_item.assert_not_called()
        assert mock_data_service.insert_playlist.call_count == 1
        assert mock_data_service.insert_playlist_item.call_count == 3

        inserted_video_ids = {
            call.kwargs["video_id"]
            for call in mock_data_service.insert_playlist_item.call_args_list
        }
        assert inserted_video_ids == {"vidAAAAAAAA", "vidBBBBBBBB", "vidCCCCCCCC"}

        # Sources are never touched -- no op targets a source's youtube_playlist_id.
        for call in mock_data_service.insert_playlist_item.call_args_list:
            assert call.kwargs["playlist_id"] == {
                "youtube_playlist_id": "PL_NEW_1", "title": "My Mix",
                "description": None, "privacy_status": "private",
            }


class TestPlanCopyNoOp:
    """AC2: re-running plan_copy against a target that already has every
    item produces zero ops."""

    def test_plan_copy_no_op_when_target_already_has_every_item(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A2", video_id="vidBBBBBBBB", position=1,
        )
        # Seed the target's cache directly as-if a real re-sync had already
        # captured a prior copy's result -- apply_plan itself never writes
        # back into the local PlaylistItem cache (that's a separate re-sync
        # step, out of this story's scope), so this test seeds that
        # post-apply state explicitly rather than actually running apply.
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        _seed_item(
            test_db, target.id,
            youtube_playlist_item_id="T1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, target.id,
            youtube_playlist_item_id="T2", video_id="vidBBBBBBBB", position=1,
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_copy(
            user_id=test_user.id,
            source_playlist_ids=["PL_A"],
            target_playlist_id=target.id,
        )

        assert plan is not None
        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []


class TestPlanCopyCollision:
    """AC3: title collision defaults to reuse-with-warning; force_new bypasses it."""

    def _seed_source_and_existing_target(
        self, test_db: Session, test_user: User
    ) -> Playlist:
        source = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        return _seed_playlist(test_db, test_user.id, "PL_EXISTING", title="My Mix")

    def test_plan_copy_collision_default_reuses_with_warning(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        existing_target = self._seed_source_and_existing_target(test_db, test_user)

        service = _make_copy_planning_service(test_db)
        plan = service.plan_copy(
            user_id=test_user.id,
            source_playlist_ids=["PL_A"],
            target_title="My Mix",
        )

        assert plan is not None
        assert plan.params["target_playlist_id"] == existing_target.id
        assert len(plan.params["warnings"]) == 1

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert all(op.op_type != "insert_playlist" for op in ops)
        assert len(ops) == 1
        assert ops[0].op_type == "insert_playlist_item"
        assert ops[0].payload["playlist_id"] == "PL_EXISTING"
        assert ops[0].depends_on_sequence is None

    def test_plan_copy_collision_force_new_creates_second_playlist(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        self._seed_source_and_existing_target(test_db, test_user)

        service = _make_copy_planning_service(test_db)
        plan = service.plan_copy(
            user_id=test_user.id,
            source_playlist_ids=["PL_A"],
            target_title="My Mix",
            force_new=True,
        )

        assert plan is not None
        assert plan.params["warnings"] == []
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert ops[0].op_type == "insert_playlist"
        assert ops[0].payload["title"] == "My Mix"


class TestPlanCopyResume:
    """AC4: a not-yet-existing target is created exactly once even when
    apply halts (via budget) between the create op and the item inserts."""

    def test_plan_copy_resume_interrupted_apply_resumes_item_inserts(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_A")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A2", video_id="vidBBBBBBBB", position=1,
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_copy(
            user_id=test_user.id,
            source_playlist_ids=["PL_A"],
            target_title="Brand New Mix",
        )
        assert plan is not None

        plan_repository = PlanRepository(test_db)
        ops = plan_repository.get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == [
            "insert_playlist", "insert_playlist_item", "insert_playlist_item",
        ]
        assert ops[1].depends_on_sequence == 0
        assert ops[2].depends_on_sequence == 0

        created_playlist_result = {
            "youtube_playlist_id": "PL_NEW_777", "title": "Brand New Mix",
            "description": None, "privacy_status": "private",
        }
        mock_data_service = MagicMock()
        mock_data_service.insert_playlist.return_value = created_playlist_result
        mock_data_service.insert_playlist_item.return_value = {
            "youtube_playlist_item_id": "PLI_NEW", "playlist_id": "PL_NEW_777",
            "video_id": "unused", "position": 0,
        }

        with patch(
            "src.services.plan_apply_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            # op0 costs exactly 50 units; op1 (also 50) can't fit in the
            # same call, so the executor's existing budget-halt logic stops
            # the run right after the create -- no interruption mock needed.
            apply_plan(plan.id, test_user.id, budget_units=50, db=test_db)

            ops_after_first_call = {
                op.sequence: op for op in plan_repository.get_ops_for_plan(plan.id)
            }
            assert ops_after_first_call[0].status == "done"
            assert ops_after_first_call[1].status == "pending"
            assert ops_after_first_call[2].status == "pending"
            assert plan_repository.get_by_id(plan.id).status == "applying"

            apply_plan(plan.id, test_user.id, budget_units=1000, db=test_db)

        assert mock_data_service.insert_playlist.call_count == 1
        assert mock_data_service.insert_playlist_item.call_count == 2
        for call in mock_data_service.insert_playlist_item.call_args_list:
            assert call.kwargs["playlist_id"] == created_playlist_result

        ops_after_second_call = plan_repository.get_ops_for_plan(plan.id)
        assert all(op.status == "done" for op in ops_after_second_call)
        assert plan_repository.get_by_id(plan.id).status == "done"


class TestPlanCopyOnDemandSource:
    """Bonus (not one of AC1-4): a not-yet-cached source is synced on
    demand, its read logged to the quota ledger, and never journaled as a
    PlanOp -- proving GOTCHA 2's resolution directly."""

    def test_not_yet_cached_public_source_is_synced_on_demand(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_copy_planning_service(test_db, mock_google_auth_service)

        mock_data_service = MagicMock()
        mock_data_service.get_playlist.return_value = {
            "id": "PL_PUBLIC_1",
            "snippet": {"title": "Public Mix", "description": None},
            "status": {"privacyStatus": "public"},
            "contentDetails": {"itemCount": 1},
        }
        mock_data_service.list_playlist_items.return_value = iter([
            [{
                "id": "PLI_X1",
                "snippet": {
                    "title": "Song X", "channelTitle": "Chan", "position": 0,
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "resourceId": {"videoId": "vidXXXXXXXX"},
                },
                "status": {"privacyStatus": "public"},
                "contentDetails": {
                    "videoId": "vidXXXXXXXX",
                    "videoPublishedAt": "2024-01-01T00:00:00Z",
                },
            }]
        ])

        with patch(
            "src.services.playlist_sync_service.YouTubeDataService",
            return_value=mock_data_service,
        ):
            plan = service.plan_copy(
                user_id=test_user.id,
                source_playlist_ids=["PL_PUBLIC_1"],
                target_title="My Mix",
            )

        assert plan is not None
        cached = PlaylistRepository(test_db).get_by_youtube_id(test_user.id, "PL_PUBLIC_1")
        assert cached is not None
        assert cached.is_owned is False
        assert cached.title == "Public Mix"

        # Two reads logged (1 playlists.list + 1 playlistItems.list page),
        # neither journaled as a PlanOp -- the plan's only ops are the
        # actual copy ops (create + one item insert).
        units_used = QuotaRepository(test_db).get_units_used_since(datetime(2000, 1, 1))
        assert units_used == 2

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == ["insert_playlist", "insert_playlist_item"]


class TestPlanAddUrls:
    """AC1: every listed URL format resolves to the correct video_id; a
    malformed URL is rejected when the plan is generated, before any
    PlanOp (or quota) is spent."""

    def test_every_url_format_resolves_to_the_correct_video_id(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        service = _make_copy_planning_service(test_db)
        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=[
                "https://www.youtube.com/watch?v=vidAAAAAAAA",
                "https://youtu.be/vidBBBBBBBB",
                "https://youtube.com/shorts/vidCCCCCCCC",
                "https://www.youtube.com/embed/vidDDDDDDDD",
                "https://www.youtube.com/live/vidEEEEEEEE",
                "vidFFFFFFFF",
            ],
            target_playlist_id=target.id,
        )

        assert plan is not None
        assert plan.kind == "add_url"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == ["insert_playlist_item"] * 6
        assert {op.payload["video_id"] for op in ops} == {
            "vidAAAAAAAA", "vidBBBBBBBB", "vidCCCCCCCC",
            "vidDDDDDDDD", "vidEEEEEEEE", "vidFFFFFFFF",
        }
        for op in ops:
            assert op.payload["playlist_id"] == "PL_TARGET"

    def test_malformed_url_rejected_before_any_op_is_created(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        service = _make_copy_planning_service(test_db)

        with pytest.raises(InvalidVideoIdError):
            service.plan_add_urls(
                user_id=test_user.id,
                urls=["https://vimeo.com/123456789"],
                target_playlist_id=target.id,
            )

    def test_missing_target_playlist_id_returns_none(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_copy_planning_service(test_db)
        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=["vidAAAAAAAA"],
            target_playlist_id="does-not-exist",
        )
        assert plan is None


class TestPlanAddUrlsListExpansion:
    """AC2: a list= URL in the input correctly expands into a copy-style
    plan sourced from that playlist, by delegating to plan_copy."""

    def test_list_url_delegates_to_plan_copy(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="S1", video_id="vidAAAAAAAA", position=0,
        )
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")

        service = _make_copy_planning_service(test_db)
        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=["https://www.youtube.com/playlist?list=PL_SOURCE"],
            target_playlist_id=target.id,
        )

        assert plan is not None
        assert plan.kind == "copy"
        assert plan.params["source_playlist_ids"] == ["PL_SOURCE"]
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == ["insert_playlist_item"]
        assert ops[0].payload["video_id"] == "vidAAAAAAAA"

    def test_mixing_video_urls_with_a_list_url_is_rejected(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        service = _make_copy_planning_service(test_db)

        with pytest.raises(ValueError):
            service.plan_add_urls(
                user_id=test_user.id,
                urls=[
                    "https://www.youtube.com/watch?v=vidAAAAAAAA",
                    "https://www.youtube.com/playlist?list=PL_SOURCE",
                ],
                target_playlist_id=target.id,
            )


class TestPlanAddUrlsSkipExisting:
    """AC3: a video already in the target playlist is skipped with a
    notice, not duplicated."""

    def test_existing_video_is_skipped_with_a_notice_and_not_duplicated(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        _seed_item(
            test_db, target.id,
            youtube_playlist_item_id="T1", video_id="vidAAAAAAAA", position=0,
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=[
                "https://www.youtube.com/watch?v=vidAAAAAAAA",
                "https://www.youtube.com/watch?v=vidBBBBBBBB",
            ],
            target_playlist_id=target.id,
        )

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == ["insert_playlist_item"]
        assert ops[0].payload["video_id"] == "vidBBBBBBBB"
        assert len(plan.params["warnings"]) == 1
        assert "vidAAAAAAAA" in plan.params["warnings"][0]


class TestPlanAddUrlsBatch:
    """AC4: batch-pasting multiple URLs at once produces a single plan
    covering all of them."""

    def test_batch_of_urls_produces_a_single_plan_with_all_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        service = _make_copy_planning_service(test_db)

        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=[
                "https://www.youtube.com/watch?v=vidAAAAAAAA",
                "https://youtu.be/vidBBBBBBBB",
                "vidCCCCCCCC",
                "vidAAAAAAAA",  # duplicate within the batch -- deduped first-seen
            ],
            target_playlist_id=target.id,
        )

        assert plan is not None
        assert plan.kind == "add_url"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 3
        assert {op.payload["video_id"] for op in ops} == {
            "vidAAAAAAAA", "vidBBBBBBBB", "vidCCCCCCCC",
        }

    def test_batch_with_new_target_title_creates_playlist_and_items_via_ref(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        service = _make_copy_planning_service(test_db)

        plan = service.plan_add_urls(
            user_id=test_user.id,
            urls=["vidAAAAAAAA", "vidBBBBBBBB"],
            target_title="Brand New List",
        )

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == [
            "insert_playlist", "insert_playlist_item", "insert_playlist_item",
        ]
        assert ops[1].payload["playlist_id"] == {"kind": "ref", "ref_sequence": 0}
        assert ops[1].depends_on_sequence == 0
        assert ops[2].depends_on_sequence == 0


class TestPlanMove:
    """`plan_move` emits a paired
    insert-into-target + delete-from-source op per matched video, with the
    delete depending on its own paired insert (not any other item's) --
    persistence-shape checks re-fetch via `PlanRepository.get_ops_for_plan`
    rather than trusting the in-memory objects the service call returned,
    matching `TestPlanCopyResume`'s existing DB-round-trip convention."""

    def test_plan_move_emits_paired_insert_and_delete_ops_with_correct_sequence_and_dependency(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        item_a = _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
        )
        item_b = _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A2", video_id="vidBBBBBBBB", position=1,
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_move(
            user_id=test_user.id,
            source_playlist_id=source.id,
            target_playlist_id=target.id,
        )

        assert plan is not None
        assert plan.kind == "move"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert [op.op_type for op in ops] == [
            "insert_playlist_item", "delete_playlist_item",
            "insert_playlist_item", "delete_playlist_item",
        ]
        assert [op.sequence for op in ops] == [0, 1, 2, 3]

        # delete@2N+1 depends on its own paired insert@2N, never the other
        # item's insert.
        assert ops[0].depends_on_sequence is None
        assert ops[1].depends_on_sequence == 0
        assert ops[2].depends_on_sequence is None
        assert ops[3].depends_on_sequence == 2

        assert ops[0].payload == {
            "playlist_id": target.youtube_playlist_id, "video_id": item_a.video_id,
        }
        assert ops[1].payload == {"playlist_item_id": item_a.youtube_playlist_item_id}
        assert ops[2].payload == {
            "playlist_id": target.youtube_playlist_id, "video_id": item_b.video_id,
        }
        assert ops[3].payload == {"playlist_item_id": item_b.youtube_playlist_item_id}

    def test_plan_move_filter_regex_only_moves_matching_titles(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidKEEPAAAA", position=0,
            title="Keep A",
        )
        skip_item = _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A2", video_id="vidSKIPBBBB", position=1,
            title="Skip B",
        )
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A3", video_id="vidKEEPCCCC", position=2,
            title="Keep C",
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_move(
            user_id=test_user.id,
            source_playlist_id=source.id,
            target_playlist_id=target.id,
            filter_regex="Keep",
        )

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 4
        moved_video_ids = {
            op.payload["video_id"] for op in ops if op.op_type == "insert_playlist_item"
        }
        assert moved_video_ids == {"vidKEEPAAAA", "vidKEEPCCCC"}
        deleted_item_ids = {
            op.payload["playlist_item_id"]
            for op in ops if op.op_type == "delete_playlist_item"
        }
        assert skip_item.youtube_playlist_item_id not in deleted_item_ids

    def test_plan_move_no_matches_produces_zero_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        source = _seed_playlist(test_db, test_user.id, "PL_SOURCE")
        target = _seed_playlist(test_db, test_user.id, "PL_TARGET")
        _seed_item(
            test_db, source.id,
            youtube_playlist_item_id="A1", video_id="vidAAAAAAAA", position=0,
            title="Nothing Matches",
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_move(
            user_id=test_user.id,
            source_playlist_id=source.id,
            target_playlist_id=target.id,
            filter_regex="NoSuchTitle",
        )

        assert plan is not None
        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []


class TestPlanReorder:
    """`plan_reorder` diffs the target
    sort order against cached `position` and emits `update_playlist_item_position`
    ops only for items whose position actually changes."""

    def test_plan_reorder_already_sorted_playlist_generates_zero_ops(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_SORTED")
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I0", video_id="vidAAAAAAAA", position=0,
            title="Alpha",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I1", video_id="vidBBBBBBBB", position=1,
            title="Bravo",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I2", video_id="vidCCCCCCCC", position=2,
            title="Charlie",
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_reorder(
            user_id=test_user.id, playlist_id=playlist.id, sort_by="title",
        )

        assert plan is not None
        assert plan.kind == "reorder"
        assert PlanRepository(test_db).get_ops_for_plan(plan.id) == []

    def test_plan_reorder_shuffled_playlist_only_updates_changed_positions(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_SHUFFLED")
        # Alphabetical target order is Alpha, Bravo, Charlie, Delta, Echo
        # (target indices 0-4). Only Bravo (currently position 0, target
        # index 1) and Alpha (currently position 1, target index 0) are
        # actually displaced -- Charlie/Delta/Echo already sit at their
        # target index, so only 2 update ops should be emitted (AC4),
        # never a full rewrite of all 5 items.
        bravo = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I0", video_id="vidBRAVOOOOO", position=0,
            title="Bravo",
        )
        alpha = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I1", video_id="vidALPHAAAAA", position=1,
            title="Alpha",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I2", video_id="vidCHARLIEEE", position=2,
            title="Charlie",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I3", video_id="vidDELTAAAAA", position=3,
            title="Delta",
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="I4", video_id="vidECHOOOOOO", position=4,
            title="Echo",
        )

        service = _make_copy_planning_service(test_db)
        plan = service.plan_reorder(
            user_id=test_user.id, playlist_id=playlist.id, sort_by="title",
        )

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 2
        assert all(op.op_type == "update_playlist_item_position" for op in ops)
        by_item_id = {op.payload["playlist_item_id"]: op.payload["position"] for op in ops}
        assert by_item_id == {
            bravo.youtube_playlist_item_id: 1,
            alpha.youtube_playlist_item_id: 0,
        }

    def test_plan_reorder_unknown_sort_by_raises_value_error(
        self, test_db: Session, test_user: User, mock_google_auth_service: MagicMock
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id, "PL_X")
        service = _make_copy_planning_service(test_db)

        with pytest.raises(ValueError):
            service.plan_reorder(
                user_id=test_user.id, playlist_id=playlist.id, sort_by="bogus",
            )
