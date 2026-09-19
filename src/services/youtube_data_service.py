"""Wrapper over the YouTube Data API v3.

The only class here that ever talks to `googleapiclient` — every other
playlist service (`playlist_sync_service.py`, `plan_apply_service.py`,
`playlist_planning_service.py`) reads or writes through this one.

Reads: `playlists.list`, `playlistItems.list`, `get_playlist`
(`playlists.list(id=...)`, not scoped to `mine=True`, for on-demand caching of
a not-yet-synced, e.g. public, playlist by ID) and an optional enrichment
read (`list_videos_batch` / `videos.list`).

Mutating writes: `insert_playlist` (`playlists.insert`),
`delete_playlist_item` (`playlistItems.delete`), `insert_playlist_item`
(`playlistItems.insert`) and `update_playlist_item_position`
(`playlistItems.update`), backing `plan_reorder`'s per-item position moves.
`plan_move` reuses `insert_playlist_item` and `delete_playlist_item` as a
paired insert-then-delete.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

PLAYLISTS_LIST_PART = "snippet,status,contentDetails"
PLAYLIST_ITEMS_LIST_PART = "snippet,status,contentDetails"
PLAYLISTS_INSERT_PART = "snippet,status"
PLAYLIST_ITEMS_INSERT_PART = "snippet"
PLAYLIST_ITEMS_UPDATE_PART = "snippet"
VIDEOS_LIST_PART = "status"
PAGE_SIZE = 50
VIDEOS_BATCH_SIZE = 50

# Google's structured `reason` codes (see error response body) that mean the
# daily quota is exhausted. Never retried — this is the "halt cleanly" case.
QUOTA_EXCEEDED_REASONS = {"quotaExceeded", "dailyLimitExceeded"}

# Transient signals worth retrying with backoff.
TRANSIENT_STATUS_CODES = {500, 502, 503, 504}
TRANSIENT_REASONS = {"backendError", "rateLimitExceeded", "internalError"}


class YouTubeDataServiceError(Exception):
    """Base exception for YouTubeDataService errors."""


class QuotaExceededError(YouTubeDataServiceError):
    """Raised when the YouTube Data API reports the daily quota is exhausted.

    Never retried — callers should halt cleanly rather than keep spending
    already-exhausted quota on retries.
    """


class PermanentAPIError(YouTubeDataServiceError):
    """Raised for a non-retryable 4xx that is not a quota failure.

    E.g. a 404/400 on a mutating call. Never retried; callers (the plan
    apply executor) should tolerate this by skipping just the offending
    operation rather than halting the whole run.
    """


def _http_error_reason(error: HttpError) -> str | None:
    """Best-effort extraction of Google's structured `reason` code.

    Parses the error body directly rather than relying on
    `googleapiclient`-internal helper attributes, which have changed shape
    across library versions.

    Args:
        error: The `HttpError` raised by a `googleapiclient` request.

    Returns:
        The first `error.errors[].reason` value, or None if the body isn't
        in the expected shape.
    """
    try:
        body = json.loads(error.content.decode("utf-8"))
        errors = body.get("error", {}).get("errors", [])
        if errors:
            return errors[0].get("reason")
    except Exception:
        logger.debug("Could not parse HttpError body for a reason code", exc_info=True)
    return None


def _is_transient(error: BaseException) -> bool:
    """Tenacity retry predicate: True only for transient (5xx/rate-limit) errors."""
    if not isinstance(error, HttpError):
        return False
    status = error.resp.status if error.resp else None
    reason = _http_error_reason(error)
    return status in TRANSIENT_STATUS_CODES or reason in TRANSIENT_REASONS


def _raise_for_http_error(error: HttpError) -> None:
    """Classify a final (non-retried-further) `HttpError` and raise accordingly.

    Args:
        error: The `HttpError` raised by a `googleapiclient` request, after
            any transient retries have already been exhausted.

    Raises:
        QuotaExceededError: If the API reports the daily quota is exhausted.
        PermanentAPIError: For any other 4xx (e.g. a 400/404 on a mutating
            call) -- non-retryable, and tolerated by the plan apply executor
            by skipping just the offending op rather than halting the plan.
        YouTubeDataServiceError: For any other API failure (e.g. no status,
            or a 5xx that survived transient retries).
    """
    status = error.resp.status if error.resp else None
    reason = _http_error_reason(error)
    if status == 403 and reason in QUOTA_EXCEEDED_REASONS:
        logger.error("YouTube Data API quota exceeded (reason=%s)", reason)
        raise QuotaExceededError(
            f"YouTube Data API quota exceeded ({reason})"
        ) from error
    if status is not None and 400 <= status < 500:
        logger.warning(
            "YouTube Data API call failed permanently (status=%s, reason=%s)",
            status, reason,
        )
        raise PermanentAPIError(f"YouTube Data API call failed: {error}") from error
    logger.exception(
        "YouTube Data API call failed (status=%s, reason=%s)", status, reason
    )
    raise YouTubeDataServiceError(f"YouTube Data API call failed: {error}") from error


_retry_transient = retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)


class YouTubeDataService:
    """Read-only wrapper over `googleapiclient.discovery.build("youtube", "v3", ...)`.

    Constructed with an already-valid, in-memory
    `google.oauth2.credentials.Credentials` object — this class never
    touches `GoogleOAuthCredential`, encryption, or the database. Building
    that credentials object from a user's stored (encrypted) tokens is
    `PlaylistSyncService`'s job.
    """

    def __init__(self, credentials: GoogleCredentials) -> None:
        """
        Initialize the service with a live googleapiclient `youtube` resource.

        Args:
            credentials: A valid, in-memory Google OAuth2 credentials object.
        """
        self._client = build(
            "youtube", "v3", credentials=credentials, cache_discovery=False
        )

    @_retry_transient
    def _execute_playlists_page(self, page_token: str | None) -> dict[str, Any]:
        """Execute one `playlists.list` page request (retried if transient)."""
        request = self._client.playlists().list(
            part=PLAYLISTS_LIST_PART,
            mine=True,
            maxResults=PAGE_SIZE,
            pageToken=page_token,
        )
        return request.execute()

    def list_my_playlists(self) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages of the caller's owned playlist resources.

        Yields:
            One list of raw `playlists.list` item resources per page (up to
            `PAGE_SIZE` each), until YouTube reports no further pages.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        page_token: str | None = None
        while True:
            try:
                response = self._execute_playlists_page(page_token)
            except HttpError as e:
                _raise_for_http_error(e)
                raise  # pragma: no cover - _raise_for_http_error always raises
            yield response.get("items", [])
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    @_retry_transient
    def _execute_playlist_items_page(
        self, playlist_id: str, page_token: str | None
    ) -> dict[str, Any]:
        """Execute one `playlistItems.list` page request (retried if transient)."""
        request = self._client.playlistItems().list(
            part=PLAYLIST_ITEMS_LIST_PART,
            playlistId=playlist_id,
            maxResults=PAGE_SIZE,
            pageToken=page_token,
        )
        return request.execute()

    def list_playlist_items(self, playlist_id: str) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages of a playlist's item resources.

        Args:
            playlist_id: YouTube's playlist ID to list items for.

        Yields:
            One list of raw `playlistItems.list` item resources per page.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        page_token: str | None = None
        while True:
            try:
                response = self._execute_playlist_items_page(playlist_id, page_token)
            except HttpError as e:
                _raise_for_http_error(e)
                raise  # pragma: no cover - _raise_for_http_error always raises
            yield response.get("items", [])
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    @_retry_transient
    def _execute_get_playlist(self, youtube_playlist_id: str) -> dict[str, Any]:
        """Execute one `playlists.list(id=...)` request (retried if transient)."""
        request = self._client.playlists().list(
            part=PLAYLISTS_LIST_PART, id=youtube_playlist_id, maxResults=1
        )
        return request.execute()

    def get_playlist(self, youtube_playlist_id: str) -> dict[str, Any] | None:
        """
        Fetch a single playlist resource by its YouTube ID.

        Unlike `list_my_playlists` (`mine=True`), this looks up a playlist by
        ID regardless of ownership -- it resolves any playlist visible to
        this API call, including a public playlist owned by someone else.
        Used by `PlaylistSyncService`'s on-demand single-playlist cache
        (copy-source resolution), not by the owned-playlist sync.

        Args:
            youtube_playlist_id: YouTube's playlist ID to fetch.

        Returns:
            The raw `playlists.list` item resource, or None if YouTube
            returns no matching playlist (deleted, private to another
            account, or a bad ID).

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        try:
            response = self._execute_get_playlist(youtube_playlist_id)
        except HttpError as e:
            _raise_for_http_error(e)
            raise  # pragma: no cover - _raise_for_http_error always raises
        items = response.get("items", [])
        return items[0] if items else None

    @_retry_transient
    def _execute_insert_playlist(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one `playlists.insert` request (retried if transient)."""
        request = self._client.playlists().insert(
            part=PLAYLISTS_INSERT_PART, body=body
        )
        return request.execute()

    def insert_playlist(
        self, title: str, description: str | None, privacy_status: str
    ) -> dict[str, Any]:
        """
        Create a new YouTube playlist owned by the authenticated user.

        Args:
            title: Playlist title.
            description: Playlist description, or None.
            privacy_status: A YouTube `privacyStatus` value (e.g. "private",
                "public", "unlisted"), passed through unvalidated.

        Returns:
            A JSON-serializable dict describing the created playlist as
            YouTube actually stored it: `youtube_playlist_id`, `title`,
            `description`, `privacy_status`.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            PermanentAPIError: For a non-retryable 4xx (e.g. an invalid
                `privacyStatus`).
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy_status},
        }
        try:
            response = self._execute_insert_playlist(body)
        except HttpError as e:
            _raise_for_http_error(e)
            raise  # pragma: no cover - _raise_for_http_error always raises
        snippet = response.get("snippet", {})
        status = response.get("status", {})
        return {
            "youtube_playlist_id": response.get("id"),
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "privacy_status": status.get("privacyStatus"),
        }

    @_retry_transient
    def _execute_insert_playlist_item(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute one `playlistItems.insert` request (retried if transient)."""
        request = self._client.playlistItems().insert(
            part=PLAYLIST_ITEMS_INSERT_PART, body=body
        )
        return request.execute()

    def insert_playlist_item(
        self, playlist_id: str | dict[str, Any], video_id: str
    ) -> dict[str, Any]:
        """
        Add one video to a YouTube playlist.

        Args:
            playlist_id: The target's YouTube playlist ID, as either a plain
                string (the target already existed at plan-generation time)
                or a dict shaped like `insert_playlist`'s return value
                (`{"youtube_playlist_id": ..., ...}`) -- the latter shape is
                what `plan_apply_service`'s ref resolution actually hands
                this method when a plan's `insert_playlist_item` op
                references a prior `insert_playlist` op's result via
                `{"kind": "ref", "ref_sequence": N}`, since ref resolution
                substitutes an op's entire persisted `result`, not a single
                field.
            video_id: YouTube video ID to add.

        Returns:
            A JSON-serializable dict describing the created playlist item as
            YouTube actually stored it: `youtube_playlist_item_id`,
            `playlist_id`, `video_id`, `position`.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            PermanentAPIError: For a non-retryable 4xx (e.g. the playlist
                doesn't exist, or the video is unavailable).
            YouTubeDataServiceError: For any other non-transient API failure.
        """
        resolved_playlist_id = (
            playlist_id["youtube_playlist_id"]
            if isinstance(playlist_id, dict)
            else playlist_id
        )
        body = {
            "snippet": {
                "playlistId": resolved_playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        try:
            response = self._execute_insert_playlist_item(body)
        except HttpError as e:
            _raise_for_http_error(e)
            raise  # pragma: no cover - _raise_for_http_error always raises
        snippet = response.get("snippet", {})
        resource_id = snippet.get("resourceId", {})
        return {
            "youtube_playlist_item_id": response.get("id"),
            "playlist_id": snippet.get("playlistId"),
            "video_id": resource_id.get("videoId"),
            "position": snippet.get("position"),
        }

    @_retry_transient
    def _execute_delete_playlist_item(self, playlist_item_id: str) -> None:
        """Execute one `playlistItems.delete` request (retried if transient)."""
        request = self._client.playlistItems().delete(id=playlist_item_id)
        request.execute()

    def delete_playlist_item(self, playlist_item_id: str) -> dict[str, Any]:
        """
        Delete a single item from a YouTube playlist.

        Args:
            playlist_item_id: YouTube's playlist item ID (not the video
                ID) -- the same value cached as
                `PlaylistItem.youtube_playlist_item_id`.

        Returns:
            A JSON-serializable confirmation dict:
            `{"playlist_item_id": ..., "deleted": True}`.
            `playlistItems.delete` itself returns no response body, so
            this is synthesized rather than mapped from an API response,
            matching `PlanOp.result`'s "must be JSON-serializable"
            contract (see `plan_apply_service._invoke_op`).

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            PermanentAPIError: For a non-retryable 4xx (e.g. the item was
                already deleted).
            YouTubeDataServiceError: For any other non-transient API
                failure.
        """
        try:
            self._execute_delete_playlist_item(playlist_item_id)
        except HttpError as e:
            _raise_for_http_error(e)
            raise  # pragma: no cover - _raise_for_http_error always raises
        return {"playlist_item_id": playlist_item_id, "deleted": True}

    @_retry_transient
    def _execute_update_playlist_item_position(
        self, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute one `playlistItems.update` request (retried if transient)."""
        request = self._client.playlistItems().update(
            part=PLAYLIST_ITEMS_UPDATE_PART, body=body
        )
        return request.execute()

    def update_playlist_item_position(
        self, playlist_item_id: str, playlist_id: str, video_id: str, position: int
    ) -> dict[str, Any]:
        """
        Move a playlist item to a new position within its playlist.

        Args:
            playlist_item_id: YouTube's playlist item ID (not the video
                ID) -- the same value cached as
                `PlaylistItem.youtube_playlist_item_id`. Required as the
                resource's `id` since `playlistItems.update` identifies the
                specific item row, not the video.
            playlist_id: The playlist's YouTube ID the item belongs to --
                required by the mandatory `snippet.playlistId` field on
                write, even though the item is already uniquely identified
                by `playlist_item_id`.
            video_id: YouTube video ID -- likewise required by the
                mandatory `snippet.resourceId` field on write, even though
                it does not change.
            position: The new zero-based position within the playlist.

        Returns:
            A JSON-serializable dict describing the updated playlist item
            as YouTube actually stored it: `youtube_playlist_item_id`,
            `playlist_id`, `video_id`, `position`.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            PermanentAPIError: For a non-retryable 4xx (e.g. the item no
                longer exists, or the playlist doesn't exist).
            YouTubeDataServiceError: For any other non-transient API
                failure.
        """
        body = {
            "id": playlist_item_id,
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
                "position": position,
            },
        }
        try:
            response = self._execute_update_playlist_item_position(body)
        except HttpError as e:
            _raise_for_http_error(e)
            raise  # pragma: no cover - _raise_for_http_error always raises
        snippet = response.get("snippet", {})
        resource_id = snippet.get("resourceId", {})
        return {
            "youtube_playlist_item_id": response.get("id"),
            "playlist_id": snippet.get("playlistId"),
            "video_id": resource_id.get("videoId"),
            "position": snippet.get("position"),
        }

    @_retry_transient
    def _execute_videos_list(self, video_ids: list[str]) -> dict[str, Any]:
        """Execute one `videos.list` request for up to `VIDEOS_BATCH_SIZE` IDs (retried if transient)."""
        request = self._client.videos().list(
            part=VIDEOS_LIST_PART, id=",".join(video_ids), maxResults=VIDEOS_BATCH_SIZE
        )
        return request.execute()

    def list_videos_batch(
        self, video_ids: list[str]
    ) -> Iterator[dict[str, dict[str, Any]]]:
        """
        Yield per-batch `video_id -> videos.list item resource` mappings.

        Enrichment read used to catch region-blocked/age-gated videos that
        plain `playlistItems.list` status doesn't reveal (see
        `playlist_planning_service.py::plan_purge_unavailable`) -- never
        called to generate a plan's `payload`/dispatch, only to decide
        which extra items belong in the purge candidate list.

        Args:
            video_ids: Video IDs to check (deduplicated by caller if
                desired); batched into `VIDEOS_BATCH_SIZE` (50) IDs per
                underlying `videos.list` call, matching the API's own
                per-call ID limit and its "1 unit per 50 IDs" quota cost.

        Yields:
            One dict per batch, mapping each `video_id` in that batch to
            its raw `videos.list` item resource. A `video_id` YouTube can
            no longer resolve at all (deleted, or otherwise fully
            inaccessible) is simply absent from the yielded dict for its
            batch.

        Raises:
            QuotaExceededError: If the API reports the daily quota is
                exhausted.
            YouTubeDataServiceError: For any other non-transient API
                failure.
        """
        for start in range(0, len(video_ids), VIDEOS_BATCH_SIZE):
            batch = video_ids[start : start + VIDEOS_BATCH_SIZE]
            try:
                response = self._execute_videos_list(batch)
            except HttpError as e:
                _raise_for_http_error(e)
                raise  # pragma: no cover - _raise_for_http_error always raises
            yield {item["id"]: item for item in response.get("items", [])}
