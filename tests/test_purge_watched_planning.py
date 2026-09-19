"""Tests for the `plan_purge_watched` strategy.

No test here ever reaches the network or spends real YouTube Data API
quota -- `plan_purge_watched` only ever reads the local playlist cache and
the watch-history tables, matching the pattern established in
`test_dedupe_purge_planning.py`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.orm import Session

from src.models.plan import Plan
from src.models.playlist import Playlist, PlaylistItem
from src.models.user import User
from src.models.watch_history import WatchHistoryEntry, WatchHistoryImport
from src.repositories.plan_repository import PlanRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.watch_history_repository import WatchHistoryRepository
from src.services.playlist_planning_service import (
    DELETE_PLAYLIST_ITEM_ESTIMATED_UNITS,
    PlaylistPlanningService,
)


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
) -> PlaylistItem:
    item = PlaylistItem(
        id=str(uuid4()),
        playlist_id=playlist_id,
        youtube_playlist_item_id=youtube_playlist_item_id,
        video_id=video_id,
        title=title,
        position=position,
        availability="available",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _seed_watch_entry(
    db: Session,
    user_id: str,
    *,
    video_id: str,
    watched_at: datetime,
    original_filename: str = "watch-history.json",
) -> WatchHistoryImport:
    """Seed one WatchHistoryImport with a single entry, as its own import row.

    Callers exercising AC4 (union-across-imports) call this more than
    once for the same user_id to produce multiple import rows.
    """
    import_record = WatchHistoryImport(
        id=str(uuid4()),
        user_id=user_id,
        original_filename=original_filename,
        status="completed",
        entry_count=1,
    )
    db.add(import_record)
    db.commit()
    db.refresh(import_record)

    entry = WatchHistoryEntry(
        id=str(uuid4()),
        import_id=import_record.id,
        video_id=video_id,
        watched_at=watched_at,
        title="Watched Video",
    )
    db.add(entry)
    db.commit()
    return import_record


def _make_service(test_db: Session) -> PlaylistPlanningService:
    """`plan_purge_watched` never touches Google auth/quota -- bare mocks
    are enough, matching `test_playlist_planning_service.py`'s convention
    for strategies that don't exercise those collaborators."""
    return PlaylistPlanningService(
        PlanRepository(test_db),
        PlaylistRepository(test_db),
        MagicMock(),
        MagicMock(),
        WatchHistoryRepository(test_db),
    )


class TestPlanPurgeWatched:
    """AC2/AC3/AC4/AC5 for `plan_purge_watched`."""

    def test_returns_none_for_missing_playlist(
        self, test_db: Session, test_user: User
    ) -> None:
        service = _make_service(test_db)
        assert service.plan_purge_watched(test_user.id, "nonexistent") is None

    def test_matches_watched_item_by_video_id(
        self, test_db: Session, test_user: User
    ) -> None:
        """AC2: an item whose video_id appears in watch history is removed;
        an item with no matching watch entry is left alone."""
        playlist = _seed_playlist(test_db, test_user.id)
        watched_item = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-watched",
            video_id="watchedVid1",
            position=0,
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-unwatched",
            video_id="unwatchedVid2",
            position=1,
        )
        _seed_watch_entry(
            test_db, test_user.id,
            video_id="watchedVid1",
            watched_at=datetime(2024, 1, 1),
        )

        service = _make_service(test_db)
        plan = service.plan_purge_watched(test_user.id, playlist.id)

        assert plan is not None
        assert plan.kind == "purge_watched"
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].op_type == "delete_playlist_item"
        assert ops[0].payload == {"playlist_item_id": watched_item.youtube_playlist_item_id}
        assert ops[0].estimated_units == DELETE_PLAYLIST_ITEM_ESTIMATED_UNITS

    def test_no_matches_produces_zero_ops(
        self, test_db: Session, test_user: User
    ) -> None:
        playlist = _seed_playlist(test_db, test_user.id)
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-1",
            video_id="neverWatched",
            position=0,
        )

        service = _make_service(test_db)
        plan = service.plan_purge_watched(test_user.id, playlist.id)

        assert plan is not None
        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert ops == []

    def test_watched_before_filters_to_earlier_entries_only(
        self, test_db: Session, test_user: User
    ) -> None:
        """AC3: only entries watched strictly before the cutoff qualify."""
        playlist = _seed_playlist(test_db, test_user.id)
        early_item = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-early",
            video_id="watchedEarly",
            position=0,
        )
        _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-late",
            video_id="watchedLate",
            position=1,
        )
        _seed_watch_entry(
            test_db, test_user.id,
            video_id="watchedEarly",
            watched_at=datetime(2024, 1, 1),
        )
        _seed_watch_entry(
            test_db, test_user.id,
            video_id="watchedLate",
            watched_at=datetime(2024, 6, 1),
        )

        service = _make_service(test_db)
        plan = service.plan_purge_watched(
            test_user.id, playlist.id, watched_before=datetime(2024, 3, 1)
        )

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].payload == {"playlist_item_id": early_item.youtube_playlist_item_id}
        assert plan.params["watched_before"] == datetime(2024, 3, 1).isoformat()

    def test_union_across_multiple_imports(
        self, test_db: Session, test_user: User
    ) -> None:
        """AC4: re-uploading a newer Takeout export must not lose history
        from a prior import -- a purge plan sees the union of every import."""
        playlist = _seed_playlist(test_db, test_user.id)
        item_from_first_import = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-old",
            video_id="watchedInOldImport",
            position=0,
        )
        item_from_second_import = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-new",
            video_id="watchedInNewImport",
            position=1,
        )
        _seed_watch_entry(
            test_db, test_user.id,
            video_id="watchedInOldImport",
            watched_at=datetime(2023, 1, 1),
            original_filename="watch-history-2023.json",
        )
        _seed_watch_entry(
            test_db, test_user.id,
            video_id="watchedInNewImport",
            watched_at=datetime(2024, 1, 1),
            original_filename="watch-history-2024.json",
        )

        service = _make_service(test_db)
        plan = service.plan_purge_watched(test_user.id, playlist.id)

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        removed_playlist_item_ids = {op.payload["playlist_item_id"] for op in ops}
        assert removed_playlist_item_ids == {
            item_from_first_import.youtube_playlist_item_id,
            item_from_second_import.youtube_playlist_item_id,
        }

    def test_default_constructor_builds_watch_history_repository_on_demand(
        self, test_db: Session, test_user: User
    ) -> None:
        """Omitting watch_history_repository (existing 4-positional-arg call
        sites) must not break plan_purge_watched -- the constructor falls
        back to a real WatchHistoryRepository sharing the session."""
        playlist = _seed_playlist(test_db, test_user.id)
        item = _seed_item(
            test_db, playlist.id,
            youtube_playlist_item_id="pli-1",
            video_id="watchedVid",
            position=0,
        )
        _seed_watch_entry(
            test_db, test_user.id, video_id="watchedVid", watched_at=datetime(2024, 1, 1)
        )

        service = PlaylistPlanningService(
            PlanRepository(test_db),
            PlaylistRepository(test_db),
            MagicMock(),
            MagicMock(),
        )
        plan = service.plan_purge_watched(test_user.id, playlist.id)

        ops = PlanRepository(test_db).get_ops_for_plan(plan.id)
        assert len(ops) == 1
        assert ops[0].payload == {"playlist_item_id": item.youtube_playlist_item_id}
