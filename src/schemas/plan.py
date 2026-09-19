"""Pydantic schemas for plan/apply engine request/response validation."""

import re
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlanOpResponse(BaseModel):
    """A single operation within a plan."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    sequence: int = Field(description="Position of this op within its plan")
    op_type: str = Field(description="Type of operation (unconstrained; defined by the plan's kind)")
    status: str = Field(description="One of 'pending', 'done', 'skipped', 'failed'")
    payload: dict[str, Any] | None = Field(default=None, description="Op input; may contain ref placeholders")
    result: dict[str, Any] | None = Field(default=None, description="Persisted output, set only when status='done'")
    depends_on_sequence: int | None = Field(default=None, description="Sequence of a prerequisite op in the same plan")
    estimated_units: int = Field(description="Pre-execution quota cost estimate")
    actual_units: int | None = Field(default=None, description="Units actually charged; set after execution")
    error_message: str | None = Field(default=None, description="Error detail if the op failed")
    executed_at: datetime | None = Field(default=None, description="When this op reached a terminal status")


class PlanResponse(BaseModel):
    """A plan and its ordered operations, with quota unit rollups."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    user_id: str = Field(description="Owning user's ID")
    kind: str = Field(description="Plan generation strategy that created this plan (unconstrained)")
    status: str = Field(description="One of 'pending', 'applying', 'done', 'failed'")
    params: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Opaque plan-generation input/output -- e.g. dedupe/purge_unavailable "
            "plans also carry a 'removals' list (sequence/video_id/title/position) "
            "here for dry-run review"
        ),
    )
    budget_units: int | None = Field(default=None, description="Overall unit budget/ceiling for this plan")
    created_at: datetime = Field(description="When this plan was created")
    updated_at: datetime = Field(description="When this plan was last updated")
    ops: list[PlanOpResponse] = Field(description="Ordered operations for this plan")
    total_estimated_units: int = Field(description="Sum of estimated_units across all ops")
    total_actual_units: int = Field(description="Sum of actual_units across all ops (None treated as 0)")


class CreatePlanRequestCreate(BaseModel):
    """Request body for POST /plans with kind="create"."""

    kind: Literal["create"] = Field(description="Create a new YouTube playlist")
    title: str = Field(description="Playlist title")
    description: str | None = Field(default=None, description="Playlist description")
    privacy_status: str = Field(
        description="YouTube privacyStatus value, e.g. 'private'/'public'/'unlisted'"
    )


class CreatePlanRequestDedupe(BaseModel):
    """Request body for POST /plans with kind="dedupe"."""

    kind: Literal["dedupe"] = Field(
        description="Remove duplicate videos from a playlist, keeping the first occurrence"
    )
    playlist_id: str = Field(description="ID of the cached Playlist to dedupe")


class CreatePlanRequestPurgeUnavailable(BaseModel):
    """Request body for POST /plans with kind="purge_unavailable"."""

    kind: Literal["purge_unavailable"] = Field(
        description="Remove private/deleted videos from a playlist"
    )
    playlist_id: str = Field(description="ID of the cached Playlist to purge")
    mode: Literal["deleted", "deleted_and_private"] = Field(
        default="deleted",
        description=(
            "'deleted' (conservative, default) targets only deleted items; "
            "'deleted_and_private' (aggressive) also targets privated items and "
            "always runs the videos.list enrichment pass"
        ),
    )
    enrich: bool = Field(
        default=False,
        description=(
            "Opt-in videos.list enrichment pass (1 unit per 50 IDs) to catch "
            "region-blocked/age-gated videos; always on when mode='deleted_and_private'"
        ),
    )


class CreatePlanRequestCopy(BaseModel):
    """Request body for POST /plans with kind="copy"."""

    kind: Literal["copy"] = Field(
        description="Build/copy a playlist from one or more source playlists"
    )
    source_playlist_ids: list[str] = Field(
        min_length=1,
        description=(
            "YouTube playlist IDs to union items from (not local cache IDs); "
            "a not-yet-cached source (e.g. a public playlist) is synced on demand"
        ),
    )
    target_playlist_id: str | None = Field(
        default=None, description="ID of an existing cached Playlist to copy into"
    )
    target_title: str | None = Field(
        default=None,
        description=(
            "Title for the target playlist; reuses an existing same-titled "
            "playlist by default (see force_new) or creates a new one"
        ),
    )
    filter_regex: str | None = Field(
        default=None, description="Only copy source items whose title matches this regex"
    )
    force_new: bool = Field(
        default=False,
        description=(
            "If True, always create a new target playlist even if one with "
            "target_title already exists; ignored when target_playlist_id is given"
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "CreatePlanRequestCopy":
        """Require exactly one of target_playlist_id / target_title."""
        if (self.target_playlist_id is None) == (self.target_title is None):
            raise ValueError(
                "exactly one of target_playlist_id or target_title is required"
            )
        return self

    @field_validator("filter_regex")
    @classmethod
    def _valid_regex(cls, value: str | None) -> str | None:
        """Reject an unparseable regex with a clean 422 instead of a 500 in the service."""
        if value is not None:
            try:
                re.compile(value)
            except re.error as e:
                # re.error is not a ValueError -- pydantic only converts
                # ValueError/TypeError/AssertionError into a clean 422; any
                # other exception from a validator propagates as an
                # unhandled 500 instead.
                raise ValueError(f"invalid filter_regex: {e}") from e
        return value


class CreatePlanRequestAddUrl(BaseModel):
    """Request body for POST /plans with kind="add_url"."""

    kind: Literal["add_url"] = Field(
        description="Add one or more pasted YouTube URLs/IDs to a playlist"
    )
    urls: list[str] = Field(
        min_length=1,
        description=(
            "YouTube URLs (watch?v=, youtu.be/, shorts/, embed/, live/, or a "
            "playlist page with list=) or raw 11-character video IDs, one per entry"
        ),
    )
    target_playlist_id: str | None = Field(
        default=None, description="ID of an existing cached Playlist to add into"
    )
    target_title: str | None = Field(
        default=None,
        description=(
            "Title for the target playlist; reuses an existing same-titled "
            "playlist by default or creates a new one"
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "CreatePlanRequestAddUrl":
        """Require exactly one of target_playlist_id / target_title."""
        if (self.target_playlist_id is None) == (self.target_title is None):
            raise ValueError(
                "exactly one of target_playlist_id or target_title is required"
            )
        return self


class CreatePlanRequestPurgeWatched(BaseModel):
    """Request body for POST /plans with kind="purge_watched"."""

    kind: Literal["purge_watched"] = Field(
        description="Remove playlist items already watched, per imported Takeout history"
    )
    playlist_id: str = Field(description="ID of the cached Playlist to purge")
    watched_before: datetime | None = Field(
        default=None,
        description=(
            "Only remove items watched strictly before this timestamp; omit to "
            "purge every watched item regardless of when it was watched"
        ),
    )


class CreatePlanRequestMove(BaseModel):
    """Request body for POST /plans with kind="move"."""

    kind: Literal["move"] = Field(
        description="Move a filtered set of videos from one playlist to another"
    )
    source_playlist_id: str = Field(description="ID of the cached Playlist to move videos out of")
    target_playlist_id: str = Field(description="ID of the cached Playlist to move videos into")
    filter_regex: str | None = Field(
        default=None, description="Only move source items whose title matches this regex"
    )

    @field_validator("filter_regex")
    @classmethod
    def _valid_regex(cls, value: str | None) -> str | None:
        """Reject an unparseable regex with a clean 422 instead of a 500 in the service."""
        if value is not None:
            try:
                re.compile(value)
            except re.error as e:
                raise ValueError(f"invalid filter_regex: {e}") from e
        return value


class CreatePlanRequestReorder(BaseModel):
    """Request body for POST /plans with kind="reorder"."""

    kind: Literal["reorder"] = Field(description="Reorder a playlist's items by a sort key")
    playlist_id: str = Field(description="ID of the cached Playlist to reorder")
    sort_by: Literal["title", "channel", "published", "added"] = Field(
        description=(
            "Sort key: 'title', 'channel' (uploader), 'published' (video publish "
            "date), or 'added' (date added to the playlist)"
        )
    )


CreatePlanRequest = Annotated[
    Union[
        CreatePlanRequestCreate,
        CreatePlanRequestDedupe,
        CreatePlanRequestPurgeUnavailable,
        CreatePlanRequestCopy,
        CreatePlanRequestAddUrl,
        CreatePlanRequestPurgeWatched,
        CreatePlanRequestMove,
        CreatePlanRequestReorder,
    ],
    Field(discriminator="kind"),
]


class ApplyPlanRequest(BaseModel):
    """Request body for POST /plans/{id}/apply."""

    budget_units: int | None = Field(
        default=None,
        description="Units this apply call may spend; defaults to settings.youtube_default_apply_budget",
    )


class QuotaResponse(BaseModel):
    """Global daily YouTube Data API quota status."""

    daily_limit: int = Field(description="Configured daily unit quota, shared across all users")
    used: int = Field(description="Units already spent today (Pacific time), across all users")
    remaining: int = Field(description="daily_limit - used")
