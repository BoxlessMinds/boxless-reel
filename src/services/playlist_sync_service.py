"""Service that syncs YouTube playlists into the local cache.

Pulls all of the connected user's owned playlists and their items from the
YouTube Data API, page by page, and upserts them into the local
`Playlist`/`PlaylistItem` cache so every other playlist feature can plan
against SQLite instead of the live API. Read-only — no playlist or item is
ever created, modified, or deleted on YouTube itself.
`cache_playlist_by_youtube_id` is an on-demand single-playlist variant
used to resolve a `plan_copy` source (owned or public) that isn't already
cached; `sync_owned_playlists` itself is unchanged.
"""

import logging
from datetime import datetime, timezone
from typing import Any, NamedTuple

from google.oauth2.credentials import Credentials as GoogleCredentials
from sqlalchemy.orm import Session

from src.config import settings
from src.models.playlist import Playlist, PlaylistItem
from src.repositories.playlist_repository import PlaylistRepository
from src.services.google_auth_service import (
    GOOGLE_TOKEN_URI,
    GoogleAuthService,
    get_google_auth_service,
)
from src.services.quota_service import QuotaService, get_quota_service
from src.services.youtube_data_service import YouTubeDataService

logger = logging.getLogger(__name__)

# Fixed placeholder titles YouTube substitutes for a gone video — the only
# reliable "is this item actually gone" signal the API exposes.
DELETED_VIDEO_TITLE = "Deleted video"
PRIVATE_VIDEO_TITLE = "Private video"

PLAYLISTS_LIST_ENDPOINT = "playlists.list"
PLAYLIST_ITEMS_LIST_ENDPOINT = "playlistItems.list"


def _utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime (matches this repo's DateTime columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_api_datetime(value: str | None) -> datetime | None:
    """
    Parse a YouTube API RFC3339 timestamp into a naive UTC datetime.

    Naive to match this repo's other DateTime columns (see
    `google_auth_service.py`'s `_utc_now_naive` convention) — comparisons
    against them must not mix aware and naive values.

    Args:
        value: An RFC3339 timestamp string (e.g. "2023-01-01T00:00:00Z"), or
            None.

    Returns:
        The parsed naive UTC datetime, or None if `value` is None/unparsable.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Could not parse YouTube API timestamp: %s", value)
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _classify_availability(snippet: dict[str, Any], status: dict[str, Any]) -> str:
    """
    Classify a playlist item's availability from its API snippet/status.

    YouTube doesn't expose a clean "is this video gone" flag on playlist
    items — a deleted or privated video instead shows up under a fixed
    placeholder title, which is the only reliable signal available here.

    Args:
        snippet: The item's `snippet` part from the API response.
        status: The item's `status` part (may be empty for a deleted video).

    Returns:
        One of "available" / "private" / "deleted" / "unknown".
    """
    title = snippet.get("title", "")
    if title == DELETED_VIDEO_TITLE:
        return "deleted"
    if title == PRIVATE_VIDEO_TITLE:
        return "private"
    privacy_status = status.get("privacyStatus")
    if privacy_status == "private":
        return "private"
    if privacy_status in ("public", "unlisted"):
        return "available"
    return "unknown"


class SyncResult(NamedTuple):
    """Summary of one `sync_owned_playlists()` run, for the `POST /sync` response."""

    playlists_synced: int
    items_synced: int
    quota_units_used: int
    synced_at: datetime


class PlaylistSyncService:
    """Pulls a user's owned YouTube playlists and items into the local cache."""

    def __init__(
        self,
        playlist_repository: PlaylistRepository,
        google_auth_service: GoogleAuthService,
        quota_service: QuotaService,
    ) -> None:
        """
        Initialize the service with its collaborators.

        Args:
            playlist_repository: Repository for cached Playlist/PlaylistItem rows.
            google_auth_service: Provides a valid (auto-refreshed) Google credential.
            quota_service: Records a quota-ledger row for each API page fetched.
        """
        self.playlist_repository = playlist_repository
        self.google_auth_service = google_auth_service
        self.quota_service = quota_service

    def sync_owned_playlists(self, user_id: str) -> SyncResult:
        """
        Full re-sync of a user's owned playlists and their items.

        Idempotent: existing `Playlist`/`PlaylistItem` rows are updated in
        place via the repository's upsert methods, matched on their unique
        keys — re-running this never creates duplicate rows.

        Args:
            user_id: The app user to sync playlists for.

        Returns:
            A `SyncResult` summary. Callers that need the synced `Playlist`
            rows themselves (e.g. to render a response) should follow up
            with `list_playlists(user_id, ...)` — that's also the codepath
            `GET /` uses, so a synced-then-immediately-listed playlist is
            read back exactly the way any other page load would see it.

        Raises:
            GoogleCredentialNotFoundError: If the user has no connected
                Google account.
            GoogleTokenRefreshError: If the stored access token is near/past
                expiry and refreshing it fails.
            QuotaExceededError: If the YouTube Data API reports the daily
                quota is exhausted mid-sync.
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        synced_at = _utc_now_naive()
        data_service = self._build_data_service(user_id)

        synced_playlists: list[Playlist] = []
        quota_units_used = 0
        for page in data_service.list_my_playlists():
            for raw_playlist in page:
                synced_playlists.append(
                    self._upsert_playlist(user_id, raw_playlist, synced_at)
                )
            self.quota_service.record_read(
                user_id, endpoint=PLAYLISTS_LIST_ENDPOINT, units=1
            )
            quota_units_used += 1

        items_synced = 0
        for playlist in synced_playlists:
            playlist_items_synced, pages_fetched = self._sync_items(
                user_id, playlist, data_service
            )
            items_synced += playlist_items_synced
            quota_units_used += pages_fetched

        logger.info(
            "Synced %d owned playlist(s), %d item(s) for user %s",
            len(synced_playlists), items_synced, user_id,
        )
        return SyncResult(
            playlists_synced=len(synced_playlists),
            items_synced=items_synced,
            quota_units_used=quota_units_used,
            synced_at=synced_at,
        )

    def cache_playlist_by_youtube_id(
        self, user_id: str, youtube_playlist_id: str
    ) -> Playlist | None:
        """
        On-demand cache of a single playlist by its YouTube ID.

        Used by `PlaylistPlanningService.plan_copy` to resolve a
        copy source that isn't already in the local cache -- e.g. a public
        playlist belonging to another channel. Unlike `sync_owned_playlists`
        (`playlists.list(mine=True)`), this uses `playlists.list(id=...)`,
        which resolves any playlist visible to the API call regardless of
        ownership, and always caches the result with `is_owned=False` (see
        `Playlist.is_owned`'s docstring) -- this method never attempts to
        determine whether the fetched playlist actually belongs to the
        connected account.

        Reads are logged to the quota ledger exactly like
        `sync_owned_playlists`, but nothing here is journaled as a `PlanOp`
        -- this runs during plan *generation*, before any `Plan`/`PlanOp`
        row exists, mirroring how `plan_purge_unavailable`'s optional
        enrichment pass spends quota without being journaled.

        Args:
            user_id: The app user attributed with this read, and who will
                own the resulting cache row.
            youtube_playlist_id: YouTube's playlist ID to cache.

        Returns:
            The upserted Playlist (`is_owned=False`), or `None` if YouTube
            has no such playlist (deleted, private to another account, or a
            bad ID) -- callers should map this to a 404.

        Raises:
            GoogleCredentialNotFoundError: If the user has no connected
                Google account.
            GoogleTokenRefreshError: If the stored access token is near/past
                expiry and refreshing it fails.
            QuotaExceededError: If the YouTube Data API reports the daily
                quota is exhausted mid-fetch.
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        synced_at = _utc_now_naive()
        data_service = self._build_data_service(user_id)

        raw_playlist = data_service.get_playlist(youtube_playlist_id)
        self.quota_service.record_read(
            user_id, endpoint=PLAYLISTS_LIST_ENDPOINT, units=1
        )
        if raw_playlist is None:
            logger.info(
                "No playlist found for youtube_playlist_id=%s (user=%s)",
                youtube_playlist_id, user_id,
            )
            return None

        playlist = self._upsert_playlist(user_id, raw_playlist, synced_at, is_owned=False)
        items_synced, pages_fetched = self._sync_items(user_id, playlist, data_service)
        logger.info(
            "Cached on-demand playlist %s (%d item(s), %d page(s)) for user %s",
            youtube_playlist_id, items_synced, pages_fetched, user_id,
        )
        return playlist

    def list_playlists(
        self, user_id: str, skip: int = 0, limit: int = 20
    ) -> tuple[list[tuple[Playlist, int, int]], int]:
        """
        Ownership-scoped list of a user's cached playlists, with counts.

        Cache-only — never calls the YouTube Data API. This is the read
        path `GET /` should use rather than the repository directly, since
        `duplicate_count`/`unavailable_count` aren't stored on `Playlist`
        (see `compute_counts`).

        Args:
            user_id: User ID to filter by ownership.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            `(rows, total)` where each row is
            `(playlist, duplicate_count, unavailable_count)` and `total` is
            the user's total cached playlist count (for pagination).
        """
        playlists = self.playlist_repository.list_all(user_id, skip=skip, limit=limit)
        total = self.playlist_repository.count(user_id)
        rows = [
            (
                playlist,
                self.playlist_repository.count_duplicate_video_ids(playlist.id),
                self.playlist_repository.count_unavailable_items(playlist.id),
            )
            for playlist in playlists
        ]
        return rows, total

    def get_playlist_items(
        self, playlist_id: str, user_id: str, skip: int = 0, limit: int = 20
    ) -> tuple[list[PlaylistItem], int] | None:
        """
        Ownership-scoped, paginated item list for one cached playlist.

        Cache-only — never calls the YouTube Data API.

        Args:
            playlist_id: ID of the cached playlist to list items for.
            user_id: User ID the playlist must belong to.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            `(items, total)`, or `None` if no playlist with `playlist_id`
            exists for `user_id` (callers should map this to a 404).
        """
        playlist = self.playlist_repository.get_by_id(playlist_id, user_id=user_id)
        if playlist is None:
            return None
        items = self.playlist_repository.list_items(playlist_id, skip=skip, limit=limit)
        total = self.playlist_repository.count_items(playlist_id)
        return items, total

    def compute_counts(self, playlist_id: str) -> dict[str, int]:
        """
        Compute a cached playlist's duplicate/unavailable item counts.

        These are derived from the current cache on every call rather than
        stored on the `Playlist` row (it has no such columns — see the `Playlist` model), so they
        always reflect the latest synced state with no separate persistence
        step to keep in sync.

        Args:
            playlist_id: ID of the cached playlist to compute counts for.

        Returns:
            Dict with `duplicate_count` (distinct video_ids appearing more
            than once in the playlist) and `unavailable_count` (items whose
            availability is not "available").
        """
        return {
            "duplicate_count": self.playlist_repository.count_duplicate_video_ids(
                playlist_id
            ),
            "unavailable_count": self.playlist_repository.count_unavailable_items(
                playlist_id
            ),
        }

    def _build_data_service(self, user_id: str) -> YouTubeDataService:
        """
        Build a `YouTubeDataService` from the user's stored Google credential.

        Decrypts the stored access/refresh tokens into local variables only
        — never assigns them back onto the `GoogleOAuthCredential` ORM
        instance, so a later `db.commit()` anywhere downstream cannot flush
        plaintext into the encrypted columns.

        Args:
            user_id: The app user whose connected Google account to use.

        Returns:
            A `YouTubeDataService` client ready to make read calls.
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

    def _upsert_playlist(
        self,
        user_id: str,
        raw_playlist: dict[str, Any],
        synced_at: datetime,
        is_owned: bool = True,
    ) -> Playlist:
        """Upsert one raw `playlists.list` resource into the cache.

        Args:
            user_id: User ID that owns the cached row.
            raw_playlist: A raw `playlists.list` item resource.
            synced_at: Timestamp to record as `last_synced_at`.
            is_owned: `True` for a playlist pulled via `sync_owned_playlists`
                (the caller's own playlists); `False` for one cached
                on-demand as a copy source via `cache_playlist_by_youtube_id`
                (copy-source resolution), which never confirms real ownership.
        """
        snippet = raw_playlist.get("snippet", {})
        status = raw_playlist.get("status", {})
        content_details = raw_playlist.get("contentDetails", {})
        return self.playlist_repository.upsert_playlist(
            user_id=user_id,
            youtube_playlist_id=raw_playlist["id"],
            title=snippet.get("title", ""),
            description=snippet.get("description"),
            privacy_status=status.get("privacyStatus", "unknown"),
            item_count=content_details.get("itemCount", 0),
            is_owned=is_owned,
            last_synced_at=synced_at,
        )

    def _sync_items(
        self, user_id: str, playlist: Playlist, data_service: YouTubeDataService
    ) -> tuple[int, int]:
        """
        Sync one playlist's items page by page, logging quota per page.

        Returns:
            `(items_synced, pages_fetched)` for the caller's `SyncResult` tally.
        """
        items_synced = 0
        pages_fetched = 0
        for page in data_service.list_playlist_items(playlist.youtube_playlist_id):
            for raw_item in page:
                self._upsert_item(playlist.id, raw_item)
                items_synced += 1
            self.quota_service.record_read(
                user_id, endpoint=PLAYLIST_ITEMS_LIST_ENDPOINT, units=1
            )
            pages_fetched += 1
        return items_synced, pages_fetched

    def _upsert_item(self, playlist_id: str, raw_item: dict[str, Any]) -> PlaylistItem:
        """Upsert one raw `playlistItems.list` resource into the cache."""
        snippet = raw_item.get("snippet", {})
        status = raw_item.get("status", {})
        content_details = raw_item.get("contentDetails", {})
        video_id = content_details.get("videoId") or snippet.get("resourceId", {}).get(
            "videoId", ""
        )
        return self.playlist_repository.upsert_item(
            playlist_id=playlist_id,
            youtube_playlist_item_id=raw_item["id"],
            video_id=video_id,
            title=snippet.get("title"),
            channel_title=snippet.get("channelTitle"),
            position=snippet.get("position", 0),
            availability=_classify_availability(snippet, status),
            published_at=_parse_api_datetime(content_details.get("videoPublishedAt")),
            added_at=_parse_api_datetime(snippet.get("publishedAt")),
        )


def get_playlist_sync_service(db: Session) -> PlaylistSyncService:
    """Factory function for PlaylistSyncService dependency injection."""
    playlist_repository = PlaylistRepository(db)
    google_auth_service = get_google_auth_service(db)
    quota_service = get_quota_service(db)
    return PlaylistSyncService(playlist_repository, google_auth_service, quota_service)
