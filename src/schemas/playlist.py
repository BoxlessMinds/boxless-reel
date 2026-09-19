"""Pydantic schemas for playlist request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaylistResponse(BaseModel):
    """A single cached playlist, including sync-computed counts."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    youtube_playlist_id: str = Field(description="YouTube's playlist ID")
    title: str = Field(description="Playlist title")
    description: str | None = Field(default=None, description="Playlist description")
    privacy_status: str = Field(description="YouTube privacy status (e.g. 'public', 'private', 'unlisted')")
    item_count: int = Field(description="Item count as reported by the YouTube API")
    duplicate_count: int = Field(description="Number of videos appearing more than once in this playlist")
    unavailable_count: int = Field(description="Number of items with availability != 'available'")
    is_owned: bool = Field(description="False if this is a cached public playlist rather than one owned by the user")
    last_synced_at: datetime = Field(description="When this playlist was last synced")


class PlaylistListResponse(BaseModel):
    """Paginated list response for playlists."""

    items: list[PlaylistResponse] = Field(description="List of playlists")
    total: int = Field(description="Total number of matching playlists")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")


class PlaylistItemResponse(BaseModel):
    """A single cached playlist item."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    youtube_playlist_item_id: str = Field(description="YouTube's playlist item ID")
    video_id: str = Field(description="YouTube video ID (11 characters)")
    title: str | None = Field(default=None, description="Video title (may be missing for deleted/private videos)")
    channel_title: str | None = Field(default=None, description="Channel name")
    position: int = Field(description="Zero-based position within the playlist")
    availability: str = Field(description="One of 'available', 'private', 'deleted', 'unknown'")
    published_at: datetime | None = Field(default=None, description="Video's original publish date")
    added_at: datetime | None = Field(default=None, description="Date the video was added to this playlist")


class PlaylistItemListResponse(BaseModel):
    """Paginated list response for playlist items."""

    items: list[PlaylistItemResponse] = Field(description="List of playlist items")
    total: int = Field(description="Total number of matching items")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")


class SyncResponse(BaseModel):
    """Summary of a completed playlist sync run."""

    playlists_synced: int = Field(description="Number of playlists upserted during this sync")
    items_synced: int = Field(description="Number of playlist items upserted during this sync")
    quota_units_used: int = Field(description="YouTube Data API quota units spent by this sync")
    synced_at: datetime = Field(description="When this sync run completed")
