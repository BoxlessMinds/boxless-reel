"""Plan-generation strategies for mutating a YouTube playlist.

Each strategy builds a journaled `Plan` of `PlanOp` rows that the generic
apply executor (`plan_apply_service`) later runs against the YouTube Data API:

- `plan_create` — a one-op plan that creates a playlist.
- `plan_dedupe` and `plan_purge_unavailable` — delete-only strategies that
  remove duplicate or unavailable items from a cached playlist.
- `plan_purge_watched` — a third delete-only strategy that matches cached
  playlist items against imported Google Takeout watch history.
- `plan_copy` — creates a playlist (using the create-with-ref mechanism) and
  inserts items across a multi-item plan.
- `plan_move` — an insert+delete op pair per moved video, linked with
  `depends_on_sequence`.
- `plan_reorder` — a diff-only strategy emitting the
  `update_playlist_item_position` op only for items whose position changes.
"""

import logging
import re
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials as GoogleCredentials
from sqlalchemy.orm import Session

from src.config import settings
from src.models.plan import Plan, PlanOp
from src.models.playlist import Playlist, PlaylistItem
from src.repositories.plan_repository import PlanRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.repositories.watch_history_repository import WatchHistoryRepository
from src.services.google_auth_service import (
    GOOGLE_TOKEN_URI,
    GoogleAuthService,
    get_google_auth_service,
)
from src.services.exceptions import InvalidVideoIdError
from src.services.playlist_sync_service import PlaylistSyncService
from src.services.quota_service import QuotaService, get_quota_service
from src.services.youtube_data_service import YouTubeDataService
from src.utils.youtube_url_parser import extract_playlist_id, extract_video_id

logger = logging.getLogger(__name__)

# `playlists.insert` / `playlistItems.insert` / `playlistItems.delete` /
# `playlistItems.update` all cost 50 units per call (YouTube Data API v3
# quota schedule) -- see CONTEXT/story-config.yaml's `quota.costs`, and the
# PRD's F3/F4/F9/F10 math ("~50/item", "100 units/video" for move's
# insert+delete pair, "50 units/moved item" for reorder).
INSERT_PLAYLIST_ESTIMATED_UNITS = 50
INSERT_PLAYLIST_ITEM_ESTIMATED_UNITS = 50
DELETE_PLAYLIST_ITEM_ESTIMATED_UNITS = 50
UPDATE_PLAYLIST_ITEM_POSITION_ESTIMATED_UNITS = 50

VIDEOS_LIST_ENDPOINT = "videos.list"

# Locked-in defaults for a target playlist `plan_copy` must create -- not
# exposed on `CreatePlanRequestCopy`; not configurable in this story.
COPY_TARGET_PRIVACY_STATUS = "private"

# "deleted" (conservative, default) only targets items already flagged
# unavailable via a placeholder title; "deleted_and_private" (aggressive)
# additionally targets privated items and always runs the enrichment pass.
PURGE_MODE_DELETED = "deleted"
PURGE_MODE_DELETED_AND_PRIVATE = "deleted_and_private"
PURGE_MODES = (PURGE_MODE_DELETED, PURGE_MODE_DELETED_AND_PRIVATE)

# `plan_reorder`'s `sort_by` -> cached `PlaylistItem` attribute it sorts on.
REORDER_SORT_BY_FIELD = {
    "title": "title",
    "channel": "channel_title",
    "published": "published_at",
    "added": "added_at",
}
REORDER_SORT_KEYS = tuple(REORDER_SORT_BY_FIELD)


def _removal_candidate(sequence: int, item: PlaylistItem) -> dict[str, Any]:
    """Build one dry-run display entry for an item slated for removal.

    Kept separate from the op's `payload` (which carries only what
    `delete_playlist_item` actually needs) so that AC3's title/position
    display never risks leaking an unexpected kwarg into the executor's
    `getattr(data_service, op_type)(**payload)` dispatch.

    Args:
        sequence: The item's position within the removal list (matches
            its op's `sequence`, when an op is emitted for it).
        item: The cached playlist item slated for removal.

    Returns:
        A JSON-serializable dict with the fields a user needs to sanity
        check the removal before applying: sequence, video_id, title,
        position.
    """
    return {
        "sequence": sequence,
        "video_id": item.video_id,
        "title": item.title,
        "position": item.position,
    }


def _move_candidate(index: int, item: PlaylistItem) -> dict[str, Any]:
    """Build one dry-run display entry for a video `plan_move` will move.

    Args:
        index: The item's 0-based index among `plan_move`'s deduped
            matched items -- its op pair lands at sequence `2*index` /
            `2*index+1`.
        item: The cached source playlist item being moved.

    Returns:
        A JSON-serializable dict: video_id, title, insert_sequence,
        delete_sequence.
    """
    return {
        "video_id": item.video_id,
        "title": item.title,
        "insert_sequence": 2 * index,
        "delete_sequence": 2 * index + 1,
    }


def _reorder_candidate(item: PlaylistItem, to_position: int) -> dict[str, Any]:
    """Build one dry-run display entry for an item `plan_reorder` will move.

    Args:
        item: The cached playlist item being repositioned.
        to_position: The item's new target position (0-based).

    Returns:
        A JSON-serializable dict: video_id, title, from_position (the
        item's current cached position), to_position.
    """
    return {
        "video_id": item.video_id,
        "title": item.title,
        "from_position": item.position,
        "to_position": to_position,
    }


class PlaylistPlanningService:
    """Generates `Plan`/`PlanOp` rows for playlist-mutation strategies.

    Generating a plan never touches the YouTube API or the quota ledger,
    with one deliberate exception: `plan_purge_unavailable`'s optional
    enrichment pass, which reads `videos.list` (never writes) to decide
    which extra items belong in the plan it produces. Only `apply_plan`
    (the apply executor) ever writes to YouTube.
    """

    def __init__(
        self,
        plan_repository: PlanRepository,
        playlist_repository: PlaylistRepository,
        google_auth_service: GoogleAuthService,
        quota_service: QuotaService,
        watch_history_repository: WatchHistoryRepository | None = None,
    ) -> None:
        """
        Initialize the service with its collaborators.

        Args:
            plan_repository: Repository used to persist the generated
                `Plan`/`PlanOp` rows.
            playlist_repository: Repository for the local `Playlist`/
                `PlaylistItem` cache that dedupe/purge plan against.
            google_auth_service: Provides a valid (auto-refreshed) Google
                credential for the optional enrichment read.
            quota_service: Records a quota-ledger row for each
                enrichment `videos.list` call.
            watch_history_repository: Provides `plan_purge_watched`'s
                watched-video-id lookup. Optional (defaulting to a plain
                `WatchHistoryRepository` sharing `playlist_repository`'s
                session) so every existing call site constructing this
                service with 4 positional args keeps working unchanged.
        """
        self.plan_repository = plan_repository
        self.playlist_repository = playlist_repository
        self.google_auth_service = google_auth_service
        self.quota_service = quota_service
        self.watch_history_repository = (
            watch_history_repository
            or WatchHistoryRepository(playlist_repository.db)
        )

    def plan_create(
        self,
        user_id: str,
        title: str,
        description: str | None,
        privacy_status: str,
    ) -> Plan:
        """
        Generate a one-op Plan that creates a new YouTube playlist.

        The single `PlanOp` uses `op_type="insert_playlist"` -- a literal
        `YouTubeDataService` method name, since `plan_apply_service`'s
        `_invoke_op` dispatches via `getattr(data_service, op_type)` with no
        alias/dispatch layer.

        Args:
            user_id: The app user this plan belongs to.
            title: Playlist title.
            description: Playlist description, or None.
            privacy_status: A YouTube `privacyStatus` value (e.g. "private",
                "public", "unlisted") -- passed through unvalidated to
                `insert_playlist` at apply time.

        Returns:
            The persisted Plan, with its single PlanOp already created.
        """
        payload = {
            "title": title,
            "description": description,
            "privacy_status": privacy_status,
        }
        plan = self.plan_repository.create_plan(
            Plan(user_id=user_id, kind="create", params=payload)
        )
        self.plan_repository.create_ops(
            [
                PlanOp(
                    plan_id=plan.id,
                    sequence=0,
                    op_type="insert_playlist",
                    payload=payload,
                    estimated_units=INSERT_PLAYLIST_ESTIMATED_UNITS,
                )
            ]
        )
        logger.info("Created 'create' plan %s for user=%s", plan.id, user_id)
        return plan

    def plan_copy(
        self,
        user_id: str,
        source_playlist_ids: list[str],
        target_playlist_id: str | None = None,
        target_title: str | None = None,
        filter_regex: str | None = None,
        force_new: bool = False,
    ) -> Plan | None:
        """
        Generate a plan that unions items from one or more source playlists
        into a target playlist, creating the target if needed.

        `source_playlist_ids` are YouTube playlist IDs (not local cache
        IDs) -- a source already in the local cache is read from there; a
        not-yet-cached source (e.g. a public playlist) is synced on demand
        via `PlaylistSyncService.cache_playlist_by_youtube_id`, a cheap read
        logged to the quota ledger but never journaled as a `PlanOp` (same
        convention as `plan_purge_unavailable`'s optional enrichment pass).

        Exactly one of `target_playlist_id` / `target_title` must be given
        (enforced by `CreatePlanRequestCopy`, not re-validated here).
        `target_playlist_id` selects an existing cached playlist directly --
        no collision question applies, and `force_new` has no effect.
        `target_title` triggers the collision rule: by default, a same-titled
        existing playlist is reused (and a `warnings` entry is added to
        `Plan.params`); `force_new=True` always creates a new one instead
        even if a same-titled playlist exists.

        Items are deduped by `video_id` across all sources (first-seen
        wins, matching `plan_dedupe`'s convention) and against whatever the
        target already contains. `filter_regex`, if given, is applied to
        each item's title *before* dedup, so a would-be-filtered-out
        occurrence never wins the first-seen slot for its `video_id`,
        excluding both non-matching titles and title=None items.

        If the target doesn't exist yet, one `insert_playlist` op is
        prepended at `sequence=0` and every `insert_playlist_item` op
        references its result via `{"kind": "ref", "ref_sequence": 0}`,
        reusing `plan_create`'s ref-resolution mechanism unchanged
        -- including `depends_on_sequence=0` on each dependent op, so a
        failed create cleanly `skip`s every item op instead of each one
        hard-failing on ref resolution.

        Never emits a `delete_playlist_item` op, and never targets a source
        playlist with any op -- sources are only ever read (see
        "## Out of scope": no add-by-URL, no deleting from sources).

        Args:
            user_id: The app user this plan belongs to.
            source_playlist_ids: YouTube playlist IDs to union items from;
                must be non-empty.
            target_playlist_id: ID of an existing cached Playlist to copy
                into. Mutually exclusive with `target_title`.
            target_title: Title for the target playlist. Mutually exclusive
                with `target_playlist_id`.
            filter_regex: Optional regex; only source items whose title
                matches (via `re.search`) are copied.
            force_new: If True, always create a new target playlist even if
                one titled `target_title` already exists. Ignored when
                `target_playlist_id` is given.

        Returns:
            The persisted Plan (zero ops if every candidate item already
            exists in the target), or `None` if `target_playlist_id` doesn't
            exist for `user_id`, or a `source_playlist_ids` entry resolves to
            no playlist on YouTube at all (callers should map either to a
            404).

        Raises:
            ValueError: If `source_playlist_ids` is empty, if neither or
                both of `target_playlist_id`/`target_title` are given, or if
                `filter_regex` is not a valid regex.
            GoogleCredentialNotFoundError: If an on-demand source fetch runs
                and the user has no connected Google account.
            GoogleTokenRefreshError: If an on-demand source fetch runs and
                the stored access token is near/past expiry and refreshing
                it fails.
            QuotaExceededError: If an on-demand source fetch runs and the
                API reports the daily quota is exhausted mid-fetch.
            YouTubeDataServiceError: For any other non-transient on-demand
                source fetch failure.
        """
        if not source_playlist_ids:
            raise ValueError("source_playlist_ids must be non-empty")
        if (target_playlist_id is None) == (target_title is None):
            raise ValueError(
                "exactly one of target_playlist_id or target_title is required"
            )
        pattern = self._compile_filter(filter_regex)

        source_items = self._resolve_source_items(user_id, source_playlist_ids)
        if source_items is None:
            return None

        if pattern is not None:
            source_items = [
                item for item in source_items
                if item.title is not None and pattern.search(item.title)
            ]

        deduped: dict[str, PlaylistItem] = {}
        for item in source_items:
            deduped.setdefault(item.video_id, item)

        warnings: list[str] = []
        target_playlist: Playlist | None = None
        create_op_needed = False

        if target_playlist_id is not None:
            target_playlist = self.playlist_repository.get_by_id(
                target_playlist_id, user_id=user_id
            )
            if target_playlist is None:
                return None
        else:
            existing = (
                None if force_new
                else self._find_owned_playlist_by_title(user_id, target_title)
            )
            if existing is not None:
                target_playlist = existing
                warnings.append(
                    f"Reusing existing playlist {existing.id!r} titled "
                    f"{target_title!r}; pass force_new=True to always create "
                    "a new one."
                )
            else:
                create_op_needed = True

        existing_target_video_ids: set[str] = set()
        if target_playlist is not None:
            existing_target_video_ids = {
                item.video_id
                for item in self.playlist_repository.list_all_items(target_playlist.id)
            }

        to_insert = [
            item for item in deduped.values()
            if item.video_id not in existing_target_video_ids
        ]

        plan = self.plan_repository.create_plan(
            Plan(
                user_id=user_id,
                kind="copy",
                params={
                    "source_playlist_ids": source_playlist_ids,
                    "target_playlist_id": target_playlist.id if target_playlist else None,
                    "target_title": target_title,
                    "filter_regex": filter_regex,
                    "force_new": force_new,
                    "warnings": warnings,
                },
            )
        )

        ops: list[PlanOp] = []
        sequence = 0
        if create_op_needed:
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=sequence,
                    op_type="insert_playlist",
                    payload={
                        "title": target_title,
                        "description": None,
                        "privacy_status": COPY_TARGET_PRIVACY_STATUS,
                    },
                    estimated_units=INSERT_PLAYLIST_ESTIMATED_UNITS,
                )
            )
            target_ref_sequence = sequence
            sequence += 1

        for item in to_insert:
            if create_op_needed:
                playlist_id_payload: Any = {"kind": "ref", "ref_sequence": target_ref_sequence}
                depends_on_sequence: int | None = target_ref_sequence
            else:
                playlist_id_payload = target_playlist.youtube_playlist_id
                depends_on_sequence = None
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=sequence,
                    op_type="insert_playlist_item",
                    payload={"playlist_id": playlist_id_payload, "video_id": item.video_id},
                    depends_on_sequence=depends_on_sequence,
                    estimated_units=INSERT_PLAYLIST_ITEM_ESTIMATED_UNITS,
                )
            )
            sequence += 1

        if ops:
            self.plan_repository.create_ops(ops)

        logger.info(
            "Created 'copy' plan %s for user=%s (%d source(s), %d op(s))",
            plan.id, user_id, len(source_playlist_ids), len(ops),
        )
        return plan

    def plan_add_urls(
        self,
        user_id: str,
        urls: list[str],
        target_playlist_id: str | None = None,
        target_title: str | None = None,
    ) -> Plan | None:
        """
        Generate a plan that adds one or more pasted YouTube URLs/IDs to a
        target playlist, creating the target if needed.

        Each entry in `urls` is parsed independently: an entry that
        resolves to a video ID (via `youtube_url_parser.extract_video_id`
        -- watch?v=, youtu.be/, shorts/, embed/, live/, or a raw
        11-character ID) is queued for individual insertion; an entry with
        no video ID but a `list=` playlist ID (e.g. a playlist page URL)
        is queued for playlist-copy expansion instead. A malformed entry
        -- no video ID and no `list=` playlist ID -- raises immediately,
        before any `PlanOp` (or quota) is spent (AC1).

        Mixing individual video entries with a playlist entry in the same
        call is rejected (`ValueError`): a `list=` URL is defined as
        expanding into a copy-style plan sourced from that playlist (AC2),
        delegating wholesale to `plan_copy` -- which only accepts playlist
        sources, never arbitrary video IDs, and changing that is out of
        scope here. Submit a playlist URL
        alone to copy it, or one or more individual video URLs/IDs in one
        batch (AC4) to add them directly.

        Individual-video entries are deduped first-seen (matching
        `plan_copy`'s convention) and, like `plan_copy`, skipped with a
        `warnings` notice -- never a duplicate insert op -- when already
        present in the target (AC3).

        Exactly one of `target_playlist_id` / `target_title` must be
        given, same contract as `plan_copy`; a `target_title` collision
        with an existing playlist is always reused (no `force_new` escape
        hatch here -- out of scope for this story).

        Args:
            user_id: The app user this plan belongs to.
            urls: YouTube URLs/IDs to add, one per entry; must contain at
                least one non-blank entry.
            target_playlist_id: ID of an existing cached Playlist to add
                into. Mutually exclusive with `target_title`.
            target_title: Title for the target playlist. Mutually
                exclusive with `target_playlist_id`.

        Returns:
            The persisted Plan (zero ops if every candidate video already
            exists in the target), or `None` if `target_playlist_id`
            doesn't exist for `user_id` (callers should map this to a
            404).

        Raises:
            ValueError: If `urls` has no non-blank entries, if neither or
                both of `target_playlist_id`/`target_title` are given, or
                if `urls` mixes individual video entries with a playlist
                (`list=`) entry.
            InvalidVideoIdError: If an entry is neither a recognized video
                URL/ID nor a playlist URL.
            GoogleCredentialNotFoundError: If a `list=` entry's on-demand
                source fetch runs and the user has no connected Google
                account.
            GoogleTokenRefreshError: If a `list=` entry's on-demand source
                fetch runs and the stored access token is near/past expiry
                and refreshing it fails.
            QuotaExceededError: If a `list=` entry's on-demand source
                fetch runs and the API reports the daily quota is
                exhausted mid-fetch.
            YouTubeDataServiceError: For any other non-transient `list=`
                entry's on-demand source fetch failure.
        """
        if (target_playlist_id is None) == (target_title is None):
            raise ValueError(
                "exactly one of target_playlist_id or target_title is required"
            )

        video_ids: list[str] = []
        playlist_ids: list[str] = []
        for raw_entry in urls:
            entry = raw_entry.strip()
            if not entry:
                continue
            try:
                video_id = extract_video_id(entry)
            except InvalidVideoIdError:
                playlist_id = extract_playlist_id(entry)
                if playlist_id is None:
                    raise
                if playlist_id not in playlist_ids:
                    playlist_ids.append(playlist_id)
            else:
                if video_id not in video_ids:
                    video_ids.append(video_id)

        if not video_ids and not playlist_ids:
            raise ValueError("urls must contain at least one non-blank entry")
        if video_ids and playlist_ids:
            raise ValueError(
                "Cannot mix individual video URLs with a list= playlist URL in "
                "the same add-by-url batch; submit the playlist URL alone to "
                "copy it, or submit only individual video URLs/IDs."
            )

        if playlist_ids:
            return self.plan_copy(
                user_id=user_id,
                source_playlist_ids=playlist_ids,
                target_playlist_id=target_playlist_id,
                target_title=target_title,
            )

        warnings: list[str] = []
        target_playlist: Playlist | None = None
        create_op_needed = False

        if target_playlist_id is not None:
            target_playlist = self.playlist_repository.get_by_id(
                target_playlist_id, user_id=user_id
            )
            if target_playlist is None:
                return None
        else:
            existing = self._find_owned_playlist_by_title(user_id, target_title)
            if existing is not None:
                target_playlist = existing
                warnings.append(
                    f"Reusing existing playlist {existing.id!r} titled {target_title!r}."
                )
            else:
                create_op_needed = True

        existing_target_video_ids: set[str] = set()
        if target_playlist is not None:
            existing_target_video_ids = {
                item.video_id
                for item in self.playlist_repository.list_all_items(target_playlist.id)
            }

        to_insert = [vid for vid in video_ids if vid not in existing_target_video_ids]
        for vid in video_ids:
            if vid in existing_target_video_ids:
                warnings.append(f"Video {vid!r} already in target playlist; skipped.")

        plan = self.plan_repository.create_plan(
            Plan(
                user_id=user_id,
                kind="add_url",
                params={
                    "urls": urls,
                    "target_playlist_id": target_playlist.id if target_playlist else None,
                    "target_title": target_title,
                    "warnings": warnings,
                },
            )
        )

        ops: list[PlanOp] = []
        sequence = 0
        if create_op_needed:
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=sequence,
                    op_type="insert_playlist",
                    payload={
                        "title": target_title,
                        "description": None,
                        "privacy_status": COPY_TARGET_PRIVACY_STATUS,
                    },
                    estimated_units=INSERT_PLAYLIST_ESTIMATED_UNITS,
                )
            )
            target_ref_sequence = sequence
            sequence += 1

        for video_id in to_insert:
            if create_op_needed:
                playlist_id_payload: Any = {"kind": "ref", "ref_sequence": target_ref_sequence}
                depends_on_sequence: int | None = target_ref_sequence
            else:
                playlist_id_payload = target_playlist.youtube_playlist_id
                depends_on_sequence = None
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=sequence,
                    op_type="insert_playlist_item",
                    payload={"playlist_id": playlist_id_payload, "video_id": video_id},
                    depends_on_sequence=depends_on_sequence,
                    estimated_units=INSERT_PLAYLIST_ITEM_ESTIMATED_UNITS,
                )
            )
            sequence += 1

        if ops:
            self.plan_repository.create_ops(ops)

        logger.info(
            "Created 'add_url' plan %s for user=%s (%d url(s), %d op(s))",
            plan.id, user_id, len(urls), len(ops),
        )
        return plan

    def plan_move(
        self,
        user_id: str,
        source_playlist_id: str,
        target_playlist_id: str,
        filter_regex: str | None = None,
    ) -> Plan | None:
        """
        Generate a plan that moves a (optionally filtered) set of videos
        from one cached playlist to another, both already owned by
        `user_id`.

        Unlike `plan_copy`/`plan_add_urls`, `source_playlist_id` and
        `target_playlist_id` are both **local cache** `Playlist` IDs (the
        same convention as `plan_dedupe`'s `playlist_id`) -- both
        playlists must already exist; move never creates a target on the
        fly.

        Source items are filtered by `filter_regex` (via `_compile_filter`,
        identical semantics to `plan_copy`: `re.search` against title,
        excluding `title=None` items) and then deduped by `video_id`,
        first-seen (lowest position) wins -- matching `plan_copy`'s dedup
        convention. Deliberately does **not** additionally check whether a
        matched video already exists in the target (unlike `plan_copy`'s
        target-membership skip) -- adding that check would be a new
        plan-generation feature beyond move/reorder, out of this story's
        scope.

        Each deduped matched item emits exactly two consecutive ops,
        reusing `plan_copy`'s/`plan_dedupe`'s existing op types verbatim
        (no new `YouTubeDataService` method for move itself):
        `insert_playlist_item` into the target at `sequence=2*i`, then
        `delete_playlist_item` from the source at `sequence=2*i+1` with
        `depends_on_sequence=2*i`. This pairing is what lets the existing
        apply executor guarantee a video is never lost nor
        duplicated across an interrupted/resumed apply: the delete only
        runs once its paired insert is confirmed `"done"`, and is skipped
        (never executed) if the insert `"failed"`.

        Args:
            user_id: The app user this plan belongs to; also the required
                owner of both `source_playlist_id` and `target_playlist_id`.
            source_playlist_id: ID of the cached Playlist to move videos
                out of.
            target_playlist_id: ID of the cached Playlist to move videos
                into.
            filter_regex: Optional regex; only source items whose title
                matches (via `re.search`) are moved.

        Returns:
            The persisted Plan (zero ops if no source item matches), or
            `None` if `source_playlist_id` or `target_playlist_id` doesn't
            exist for `user_id` (callers should map either to a 404).

        Raises:
            ValueError: If `source_playlist_id == target_playlist_id`, or
                if `filter_regex` is not a valid regex.
        """
        if source_playlist_id == target_playlist_id:
            raise ValueError("source_playlist_id and target_playlist_id must differ")
        pattern = self._compile_filter(filter_regex)

        source_playlist = self.playlist_repository.get_by_id(
            source_playlist_id, user_id=user_id
        )
        if source_playlist is None:
            return None
        target_playlist = self.playlist_repository.get_by_id(
            target_playlist_id, user_id=user_id
        )
        if target_playlist is None:
            return None

        items = self.playlist_repository.list_all_items(source_playlist_id)
        if pattern is not None:
            items = [
                item for item in items
                if item.title is not None and pattern.search(item.title)
            ]

        deduped: dict[str, PlaylistItem] = {}
        for item in items:
            deduped.setdefault(item.video_id, item)
        matched = list(deduped.values())

        plan = self.plan_repository.create_plan(
            Plan(
                user_id=user_id,
                kind="move",
                params={
                    "source_playlist_id": source_playlist_id,
                    "target_playlist_id": target_playlist_id,
                    "filter_regex": filter_regex,
                    "moves": [
                        _move_candidate(i, item) for i, item in enumerate(matched)
                    ],
                },
            )
        )

        ops: list[PlanOp] = []
        for i, item in enumerate(matched):
            insert_sequence = 2 * i
            delete_sequence = 2 * i + 1
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=insert_sequence,
                    op_type="insert_playlist_item",
                    payload={
                        "playlist_id": target_playlist.youtube_playlist_id,
                        "video_id": item.video_id,
                    },
                    estimated_units=INSERT_PLAYLIST_ITEM_ESTIMATED_UNITS,
                )
            )
            ops.append(
                PlanOp(
                    plan_id=plan.id,
                    sequence=delete_sequence,
                    op_type="delete_playlist_item",
                    payload={"playlist_item_id": item.youtube_playlist_item_id},
                    depends_on_sequence=insert_sequence,
                    estimated_units=DELETE_PLAYLIST_ITEM_ESTIMATED_UNITS,
                )
            )

        if ops:
            self.plan_repository.create_ops(ops)

        logger.info(
            "Created 'move' plan %s for user=%s source=%s target=%s "
            "(%d video(s), %d op(s))",
            plan.id, user_id, source_playlist_id, target_playlist_id,
            len(matched), len(ops),
        )
        return plan

    def _compile_filter(self, filter_regex: str | None) -> re.Pattern[str] | None:
        """
        Compile `plan_copy`'s optional title filter, translating a bad
        pattern into a plain `ValueError` (mirroring
        `plan_purge_unavailable`'s `ValueError` for an invalid `mode`).

        Args:
            filter_regex: A regex string, or None.

        Returns:
            The compiled pattern, or None if `filter_regex` is None.

        Raises:
            ValueError: If `filter_regex` is not a valid regex.
        """
        if filter_regex is None:
            return None
        try:
            return re.compile(filter_regex)
        except re.error as e:
            raise ValueError(f"invalid filter_regex: {e}") from e

    def _resolve_source_items(
        self, user_id: str, source_playlist_ids: list[str]
    ) -> list[PlaylistItem] | None:
        """
        Resolve every copy source to its cached items, syncing on demand.

        Args:
            user_id: The app user requesting the copy.
            source_playlist_ids: YouTube playlist IDs to resolve.

        Returns:
            The concatenation of every source's cached items (source order,
            then position order), or `None` if any `source_playlist_ids`
            entry resolves to no playlist on YouTube at all.
        """
        sync_service = self._build_playlist_sync_service()
        items: list[PlaylistItem] = []
        for youtube_playlist_id in source_playlist_ids:
            playlist = self.playlist_repository.get_by_youtube_id(
                user_id, youtube_playlist_id
            )
            if playlist is None:
                playlist = sync_service.cache_playlist_by_youtube_id(
                    user_id, youtube_playlist_id
                )
                if playlist is None:
                    return None
            items.extend(self.playlist_repository.list_all_items(playlist.id))
        return items

    def _find_owned_playlist_by_title(self, user_id: str, title: str) -> Playlist | None:
        """
        Find one of the user's cached playlists with an exact title match.

        Implemented via `PlaylistRepository.list_all`/`count` rather than a
        new repository method, since `playlist_repository.py` is outside
        this story's file ownership.

        Args:
            user_id: The app user to search within.
            title: Exact title to match (case-sensitive).

        Returns:
            The first matching cached Playlist, or None if none match.
        """
        total = self.playlist_repository.count(user_id)
        for playlist in self.playlist_repository.list_all(user_id, skip=0, limit=max(total, 1)):
            if playlist.title == title:
                return playlist
        return None

    def _build_playlist_sync_service(self) -> PlaylistSyncService:
        """
        Build a `PlaylistSyncService` sharing this service's collaborators.

        Constructed on demand rather than injected via `__init__` so that
        `plan_copy`'s on-demand-source-caching need doesn't change this
        class's constructor signature -- avoiding a breaking change for
        every existing call site (this file's own tests, plus the dedupe/purge
        `tests/test_dedupe_purge_planning.py`, both construct
        `PlaylistPlanningService` with today's 4 positional args).

        Returns:
            A `PlaylistSyncService` wired to the same `playlist_repository`,
            `google_auth_service`, and `quota_service` this service already
            holds.
        """
        return PlaylistSyncService(
            self.playlist_repository, self.google_auth_service, self.quota_service
        )

    def plan_dedupe(self, user_id: str, playlist_id: str) -> Plan | None:
        """
        Generate a plan that removes every duplicate occurrence of a video
        within one playlist, keeping the first-seen (lowest position)
        occurrence.

        Pure local-cache read -- never calls the YouTube Data API or
        spends quota to generate this plan; only applying it later does.

        Args:
            user_id: The app user this plan belongs to; also the required
                owner of `playlist_id`.
            playlist_id: ID of the cached `Playlist` to dedupe.

        Returns:
            The persisted Plan (with zero ops if there are no
            duplicates), or `None` if no playlist with `playlist_id`
            exists for `user_id` (callers should map this to a 404).
        """
        playlist = self.playlist_repository.get_by_id(playlist_id, user_id=user_id)
        if playlist is None:
            return None

        items = self.playlist_repository.list_all_items(playlist_id)
        seen_video_ids: set[str] = set()
        duplicates: list[PlaylistItem] = []
        for item in items:
            if item.video_id in seen_video_ids:
                duplicates.append(item)
            else:
                seen_video_ids.add(item.video_id)

        plan = self._create_removal_plan(user_id, "dedupe", duplicates, extra_params={
            "playlist_id": playlist_id,
        })
        logger.info(
            "Created 'dedupe' plan %s for user=%s playlist=%s (%d duplicate(s))",
            plan.id, user_id, playlist_id, len(duplicates),
        )
        return plan

    def plan_purge_unavailable(
        self,
        user_id: str,
        playlist_id: str,
        mode: str = PURGE_MODE_DELETED,
        enrich: bool = False,
    ) -> Plan | None:
        """
        Generate a plan that removes items whose cached availability is
        unavailable.

        `mode="deleted"` (the default, conservative) only targets items
        already flagged `availability="deleted"`.
        `mode="deleted_and_private"` additionally targets
        `availability="private"` items, and unconditionally runs the
        enrichment pass below regardless of `enrich`.

        Enrichment (`enrich=True`, or forced by
        `mode="deleted_and_private"`) batch-checks every remaining
        "available"/"unknown" item's current `videos.list` status (1 unit
        per 50 IDs) to catch region-blocked or age-gated videos that plain
        playlist-item status doesn't reveal -- any `video_id`
        `YouTubeDataService.list_videos_batch` returns nothing for is no
        longer resolvable at all, and is added to the removal candidates.
        This enrichment read is the only YouTube Data API call this
        method ever makes; every other read is local-cache only.

        Args:
            user_id: The app user this plan belongs to; also the required
                owner of `playlist_id`.
            playlist_id: ID of the cached `Playlist` to purge.
            mode: `"deleted"` (conservative, default) or
                `"deleted_and_private"` (aggressive).
            enrich: Opt-in `videos.list` enrichment pass for `"deleted"`
                mode; always on for `"deleted_and_private"`.

        Returns:
            The persisted Plan (with zero ops if nothing is unavailable),
            or `None` if no playlist with `playlist_id` exists for
            `user_id` (callers should map this to a 404).

        Raises:
            ValueError: If `mode` is not one of `PURGE_MODES`.
            GoogleCredentialNotFoundError: If enrichment runs but the user
                has no connected Google account.
            GoogleTokenRefreshError: If enrichment runs and the stored
                access token is near/past expiry and refreshing it fails.
            QuotaExceededError: If enrichment runs and the API reports
                the daily quota is exhausted mid-pass.
            YouTubeDataServiceError: For any other non-transient
                enrichment API failure.
        """
        if mode not in PURGE_MODES:
            raise ValueError(
                f"Unknown purge mode: {mode!r}, expected one of {PURGE_MODES}"
            )

        playlist = self.playlist_repository.get_by_id(playlist_id, user_id=user_id)
        if playlist is None:
            return None

        items = self.playlist_repository.list_all_items(playlist_id)
        target_availabilities = (
            {"deleted"} if mode == PURGE_MODE_DELETED else {"deleted", "private"}
        )
        candidates = [item for item in items if item.availability in target_availabilities]

        run_enrichment = enrich or mode == PURGE_MODE_DELETED_AND_PRIVATE
        if run_enrichment:
            # "deleted"/"private" items are already reliably classified by
            # sync's placeholder-title check -- enrichment only adds value
            # for items sync couldn't already condemn.
            enrichment_pool = [
                item for item in items if item.availability not in ("deleted", "private")
            ]
            if enrichment_pool:
                candidates.extend(
                    self._find_unresolvable_via_enrichment(user_id, enrichment_pool)
                )

        plan = self._create_removal_plan(user_id, "purge_unavailable", candidates, extra_params={
            "playlist_id": playlist_id,
            "mode": mode,
            "enrich": run_enrichment,
        })
        logger.info(
            "Created 'purge_unavailable' plan %s for user=%s playlist=%s mode=%s "
            "enrich=%s (%d removal(s))",
            plan.id, user_id, playlist_id, mode, run_enrichment, len(candidates),
        )
        return plan

    def plan_purge_watched(
        self,
        user_id: str,
        playlist_id: str,
        watched_before: datetime | None = None,
    ) -> Plan | None:
        """
        Generate a plan that removes playlist items already watched, per
        the user's imported Google Takeout watch history.

        Matches cached playlist items against the UNION of every
        `WatchHistoryImport` the user has uploaded (never just the latest
        -- re-uploading a newer Takeout export must not lose or duplicate
        history from a prior import), by `video_id`. When `watched_before`
        is given, only items with at least one watch entry strictly before
        that timestamp are targeted. Emits the exact same
        `op_type="delete_playlist_item"` shape as `plan_dedupe`/
        `plan_purge_unavailable` via `_create_removal_plan` -- no executor
        changes required.

        Pure local-cache + watch-history read -- never calls the YouTube
        Data API or spends quota to generate this plan; only applying it
        later does.

        Args:
            user_id: The app user this plan belongs to; also the required
                owner of `playlist_id`.
            playlist_id: ID of the cached `Playlist` to purge.
            watched_before: If given, only removes items with a watch
                entry strictly before this timestamp; if None, removes
                every item that has been watched at all.

        Returns:
            The persisted Plan (with zero ops if nothing matches), or
            `None` if no playlist with `playlist_id` exists for `user_id`
            (callers should map this to a 404).
        """
        playlist = self.playlist_repository.get_by_id(playlist_id, user_id=user_id)
        if playlist is None:
            return None

        items = self.playlist_repository.list_all_items(playlist_id)
        watched_video_ids = self.watch_history_repository.list_watched_video_ids(
            user_id, watched_before
        )
        matched_items = [item for item in items if item.video_id in watched_video_ids]

        plan = self._create_removal_plan(
            user_id,
            "purge_watched",
            matched_items,
            extra_params={
                "playlist_id": playlist_id,
                "watched_before": watched_before.isoformat() if watched_before else None,
            },
        )
        logger.info(
            "Created 'purge_watched' plan %s for user=%s playlist=%s "
            "watched_before=%s (%d removal(s))",
            plan.id, user_id, playlist_id, watched_before, len(matched_items),
        )
        return plan

    def plan_reorder(self, user_id: str, playlist_id: str, sort_by: str) -> Plan | None:
        """
        Generate a plan that reorders a cached playlist's items by
        `sort_by`, emitting an update op only for items whose position
        actually changes.

        `sort_by` selects the cached field to sort on, via
        `REORDER_SORT_BY_FIELD`: `"title"`/`"channel"` sort
        case-insensitively on `title`/`channel_title`; `"published"`/
        `"added"` sort on the `published_at`/`added_at` timestamp. Items
        missing a value for the chosen key always sort last; ties
        (including every item, when the playlist is already in that order)
        are broken by current position, so re-running this against an
        unchanged playlist is fully deterministic and produces zero ops
        (AC3).

        Diffs the freshly computed target order against each item's
        current cached `position` and emits one
        `op_type="update_playlist_item_position"` op -- a new
        `YouTubeDataService` write this story adds -- only where an item's
        target index differs from its current position (AC4: never a full
        rewrite).

        Deliberately does not attempt to compute an application-order-safe
        sequence of intermediate positions -- it only decides each item's
        final target index. Applying several absolute-position updates
        against the real YouTube API can itself perturb other items'
        positions between one op and the next; resolving that is an
        application-time (apply executor) concern, out of this
        plan-generation strategy's scope.

        Args:
            user_id: The app user this plan belongs to; also the required
                owner of `playlist_id`.
            playlist_id: ID of the cached Playlist to reorder.
            sort_by: One of `REORDER_SORT_KEYS`
                (`"title"`/`"channel"`/`"published"`/`"added"`).

        Returns:
            The persisted Plan (zero ops if the playlist is already
            sorted), or `None` if no playlist with `playlist_id` exists
            for `user_id` (callers should map this to a 404).

        Raises:
            ValueError: If `sort_by` is not one of `REORDER_SORT_KEYS`.
        """
        if sort_by not in REORDER_SORT_KEYS:
            raise ValueError(
                f"Unknown sort_by: {sort_by!r}, expected one of {REORDER_SORT_KEYS}"
            )

        playlist = self.playlist_repository.get_by_id(playlist_id, user_id=user_id)
        if playlist is None:
            return None

        items = self.playlist_repository.list_all_items(playlist_id)
        field = REORDER_SORT_BY_FIELD[sort_by]

        def sort_key(item: PlaylistItem) -> tuple[bool, Any, int]:
            value = getattr(item, field)
            if isinstance(value, str):
                value = value.casefold()
            return (value is None, value, item.position)

        target_order = sorted(items, key=sort_key)
        changed = [
            (target_index, item)
            for target_index, item in enumerate(target_order)
            if target_index != item.position
        ]

        plan = self.plan_repository.create_plan(
            Plan(
                user_id=user_id,
                kind="reorder",
                params={
                    "playlist_id": playlist_id,
                    "sort_by": sort_by,
                    "reorders": [
                        _reorder_candidate(item, target_index)
                        for target_index, item in changed
                    ],
                },
            )
        )

        if changed:
            self.plan_repository.create_ops(
                [
                    PlanOp(
                        plan_id=plan.id,
                        sequence=sequence,
                        op_type="update_playlist_item_position",
                        payload={
                            "playlist_item_id": item.youtube_playlist_item_id,
                            "playlist_id": playlist.youtube_playlist_id,
                            "video_id": item.video_id,
                            "position": target_index,
                        },
                        estimated_units=UPDATE_PLAYLIST_ITEM_POSITION_ESTIMATED_UNITS,
                    )
                    for sequence, (target_index, item) in enumerate(changed)
                ]
            )

        logger.info(
            "Created 'reorder' plan %s for user=%s playlist=%s sort_by=%s "
            "(%d update(s))",
            plan.id, user_id, playlist_id, sort_by, len(changed),
        )
        return plan

    def _create_removal_plan(
        self,
        user_id: str,
        kind: str,
        removals: list[PlaylistItem],
        extra_params: dict[str, Any],
    ) -> Plan:
        """
        Persist a `Plan` plus one `delete_playlist_item` op per removal.

        Shared by `plan_dedupe` and `plan_purge_unavailable` -- both
        strategies are delete-only and differ only in how they select
        `removals`.

        Args:
            user_id: The app user this plan belongs to.
            kind: `Plan.kind` -- `"dedupe"` or `"purge_unavailable"`.
            removals: Items to emit one delete op per, in the order they
                should be numbered (their existing playlist order).
            extra_params: Strategy-specific fields (e.g. `playlist_id`,
                `mode`) merged into `Plan.params` alongside the dry-run
                `removals` display list.

        Returns:
            The persisted Plan, with one PlanOp per item in `removals`
            (zero ops if `removals` is empty).
        """
        plan = self.plan_repository.create_plan(
            Plan(
                user_id=user_id,
                kind=kind,
                params={
                    **extra_params,
                    "removals": [
                        _removal_candidate(i, item) for i, item in enumerate(removals)
                    ],
                },
            )
        )
        if removals:
            self.plan_repository.create_ops(
                [
                    PlanOp(
                        plan_id=plan.id,
                        sequence=i,
                        op_type="delete_playlist_item",
                        payload={"playlist_item_id": item.youtube_playlist_item_id},
                        estimated_units=DELETE_PLAYLIST_ITEM_ESTIMATED_UNITS,
                    )
                    for i, item in enumerate(removals)
                ]
            )
        return plan

    def _find_unresolvable_via_enrichment(
        self, user_id: str, items: list[PlaylistItem]
    ) -> list[PlaylistItem]:
        """
        Batch-check `items`' videos via `videos.list`, returning those
        YouTube no longer resolves at all.

        This is the strongest unambiguous signal that a plain-status
        "available"/"unknown" item is actually gone (e.g. region-blocked
        from this app's calling region, or otherwise inaccessible in a
        way `playlistItems.list` doesn't surface).

        Args:
            user_id: Attributed on the `videos.list` quota-ledger entries
                this makes, and used to build the enrichment
                `YouTubeDataService`.
            items: Candidate items to check.

        Returns:
            The subset of `items` whose `video_id` is missing from the
            `list_videos_batch` response.
        """
        data_service = self._build_data_service(user_id)
        # Dedupe video_ids (a video can appear more than once in a
        # playlist) while keeping a stable, testable call order.
        video_ids = list(dict.fromkeys(item.video_id for item in items))
        resolved: set[str] = set()
        for batch in data_service.list_videos_batch(video_ids):
            resolved.update(batch.keys())
            self.quota_service.record_read(user_id, endpoint=VIDEOS_LIST_ENDPOINT, units=1)
        return [item for item in items if item.video_id not in resolved]

    def _build_data_service(self, user_id: str) -> YouTubeDataService:
        """
        Build a `YouTubeDataService` from the user's stored Google credential.

        Deliberately duplicates `PlaylistSyncService`'s and
        `plan_apply_service`'s small decrypt-into-locals-then-build
        pattern rather than reusing that private method cross-service --
        matching this repo's established precedent (see
        `plan_apply_service._build_data_service`'s docstring) of keeping
        each service's YouTube-client construction independent.

        Args:
            user_id: The app user whose connected Google account to use.

        Returns:
            A `YouTubeDataService` client ready to make the enrichment
            read.

        Raises:
            GoogleCredentialNotFoundError: If the user has no connected
                Google account.
            GoogleTokenRefreshError: If the stored access token is
                near/past expiry and refreshing it fails.
        """
        credential = self.google_auth_service.get_valid_credential(user_id)
        access_token = self.google_auth_service.repository.encryption.decrypt(
            credential.access_token
        )
        refresh_token = self.google_auth_service.repository.encryption.decrypt(
            credential.refresh_token
        )
        google_credentials = GoogleCredentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            scopes=credential.scopes.split(),
        )
        return YouTubeDataService(google_credentials)


def get_playlist_planning_service(db: Session) -> PlaylistPlanningService:
    """Factory function for PlaylistPlanningService dependency injection."""
    return PlaylistPlanningService(
        plan_repository=PlanRepository(db),
        playlist_repository=PlaylistRepository(db),
        google_auth_service=get_google_auth_service(db),
        quota_service=get_quota_service(db),
        watch_history_repository=WatchHistoryRepository(db),
    )
