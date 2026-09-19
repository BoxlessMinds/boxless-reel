"""Repository for playlist and playlist item database operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.playlist import Playlist, PlaylistItem

logger = logging.getLogger(__name__)


class PlaylistRepository:
    """Data access layer for cached playlist and playlist item operations."""

    def __init__(self, db: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    # -- Playlist -----------------------------------------------------------

    def create(self, playlist: Playlist) -> Playlist:
        """
        Create a new playlist record.

        Args:
            playlist: Playlist model instance to persist.

        Returns:
            The persisted playlist with generated ID.
        """
        logger.debug(
            "Creating playlist for youtube_playlist_id: %s", playlist.youtube_playlist_id
        )
        self.db.add(playlist)
        self.db.commit()
        self.db.refresh(playlist)
        logger.debug("Created playlist with id: %s", playlist.id)
        return playlist

    def get_by_id(
        self,
        playlist_id: UUID | str,
        user_id: str | None = None,
    ) -> Playlist | None:
        """
        Get a playlist by its ID.

        Args:
            playlist_id: UUID of the playlist.
            user_id: Optional user ID to filter by ownership.

        Returns:
            Playlist if found, None otherwise.
        """
        logger.debug("Fetching playlist by id: %s (user_id=%s)", playlist_id, user_id)
        stmt = select(Playlist).where(Playlist.id == str(playlist_id))
        if user_id:
            stmt = stmt.where(Playlist.user_id == user_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Playlist not found: %s", playlist_id)
        return result

    def get_by_youtube_id(
        self,
        user_id: str,
        youtube_playlist_id: str,
    ) -> Playlist | None:
        """
        Get a playlist by its YouTube playlist ID, scoped to one user.

        Args:
            user_id: User ID that owns the cached row.
            youtube_playlist_id: YouTube's playlist ID.

        Returns:
            Playlist if found, None otherwise.
        """
        logger.debug(
            "Fetching playlist by youtube_playlist_id: %s (user_id=%s)",
            youtube_playlist_id, user_id,
        )
        stmt = select(Playlist).where(
            Playlist.user_id == user_id,
            Playlist.youtube_playlist_id == youtube_playlist_id,
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug(
                "Playlist not found for youtube_playlist_id: %s", youtube_playlist_id
            )
        return result

    def list_all(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Playlist]:
        """
        List a user's cached playlists.

        Args:
            user_id: User ID to filter by ownership.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of matching playlists.
        """
        logger.debug(
            "Listing playlists (user_id=%s, skip=%d, limit=%d)", user_id, skip, limit
        )
        stmt = (
            select(Playlist)
            .where(Playlist.user_id == user_id)
            .order_by(Playlist.title.asc())
            .offset(skip)
            .limit(limit)
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d playlists", len(results))
        return results

    def count(self, user_id: str) -> int:
        """
        Count a user's cached playlists.

        Args:
            user_id: User ID to filter by ownership.

        Returns:
            Count of matching playlists.
        """
        logger.debug("Counting playlists (user_id=%s)", user_id)
        stmt = select(func.count()).select_from(Playlist).where(Playlist.user_id == user_id)
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Count result: %d", count)
        return count

    def upsert_playlist(
        self,
        user_id: str,
        youtube_playlist_id: str,
        **fields: Any,
    ) -> Playlist:
        """
        Insert or update a playlist row, matched on the (user_id, youtube_playlist_id)
        unique key.

        Existing rows are updated in place so that re-running sync never creates
        duplicate `Playlist` rows.

        Args:
            user_id: User ID that owns the cached row.
            youtube_playlist_id: YouTube's playlist ID.
            **fields: Column values to set (e.g. title, description,
                privacy_status, item_count, is_owned, last_synced_at).

        Returns:
            The inserted or updated playlist.
        """
        logger.debug(
            "Upserting playlist (user_id=%s, youtube_playlist_id=%s)",
            user_id, youtube_playlist_id,
        )
        playlist = self.get_by_youtube_id(user_id, youtube_playlist_id)
        if playlist is None:
            playlist = Playlist(
                user_id=user_id,
                youtube_playlist_id=youtube_playlist_id,
                **fields,
            )
            self.db.add(playlist)
        else:
            for key, value in fields.items():
                setattr(playlist, key, value)
        self.db.commit()
        self.db.refresh(playlist)
        logger.debug("Upserted playlist with id: %s", playlist.id)
        return playlist

    # -- PlaylistItem ---------------------------------------------------------

    def create_item(self, item: PlaylistItem) -> PlaylistItem:
        """
        Create a new playlist item record.

        Args:
            item: PlaylistItem model instance to persist.

        Returns:
            The persisted item with generated ID.
        """
        logger.debug(
            "Creating playlist item for playlist_id: %s, video_id: %s",
            item.playlist_id, item.video_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        logger.debug("Created playlist item with id: %s", item.id)
        return item

    def get_item_by_id(self, item_id: UUID | str) -> PlaylistItem | None:
        """
        Get a playlist item by its ID.

        Args:
            item_id: UUID of the playlist item.

        Returns:
            PlaylistItem if found, None otherwise.
        """
        logger.debug("Fetching playlist item by id: %s", item_id)
        stmt = select(PlaylistItem).where(PlaylistItem.id == str(item_id))
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug("Playlist item not found: %s", item_id)
        return result

    def get_item_by_youtube_id(
        self,
        playlist_id: str,
        youtube_playlist_item_id: str,
    ) -> PlaylistItem | None:
        """
        Get a playlist item by its YouTube playlist item ID, scoped to one playlist.

        Args:
            playlist_id: ID of the owning playlist.
            youtube_playlist_item_id: YouTube's playlist item ID.

        Returns:
            PlaylistItem if found, None otherwise.
        """
        logger.debug(
            "Fetching playlist item by youtube_playlist_item_id: %s (playlist_id=%s)",
            youtube_playlist_item_id, playlist_id,
        )
        stmt = select(PlaylistItem).where(
            PlaylistItem.playlist_id == playlist_id,
            PlaylistItem.youtube_playlist_item_id == youtube_playlist_item_id,
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        if result is None:
            logger.debug(
                "Playlist item not found for youtube_playlist_item_id: %s",
                youtube_playlist_item_id,
            )
        return result

    def list_items(
        self,
        playlist_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PlaylistItem]:
        """
        List a playlist's cached items, ordered by their playlist position.

        Args:
            playlist_id: ID of the owning playlist.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.

        Returns:
            List of matching playlist items.
        """
        logger.debug(
            "Listing playlist items (playlist_id=%s, skip=%d, limit=%d)",
            playlist_id, skip, limit,
        )
        stmt = (
            select(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist_id)
            .order_by(PlaylistItem.position.asc())
            .offset(skip)
            .limit(limit)
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d playlist items", len(results))
        return results

    def list_all_items(self, playlist_id: str) -> list[PlaylistItem]:
        """
        Get every cached item in a playlist, ordered by position.

        Unpaginated, unlike `list_items` -- used by plan-generation
        strategies (dedupe, purge) that must see every item at once to
        decide what to remove, not just one page of a UI listing.

        Args:
            playlist_id: ID of the owning playlist.

        Returns:
            List of all matching playlist items ordered by ascending
            position.
        """
        logger.debug("Listing all playlist items (playlist_id=%s)", playlist_id)
        stmt = (
            select(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist_id)
            .order_by(PlaylistItem.position.asc())
        )
        results = list(self.db.execute(stmt).scalars().all())
        logger.debug("Found %d playlist items", len(results))
        return results

    def count_items(self, playlist_id: str) -> int:
        """
        Count a playlist's cached items.

        Args:
            playlist_id: ID of the owning playlist.

        Returns:
            Count of matching playlist items.
        """
        logger.debug("Counting playlist items (playlist_id=%s)", playlist_id)
        stmt = (
            select(func.count())
            .select_from(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist_id)
        )
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Count result: %d", count)
        return count

    def upsert_item(
        self,
        playlist_id: str,
        youtube_playlist_item_id: str,
        **fields: Any,
    ) -> PlaylistItem:
        """
        Insert or update a playlist item row, matched on the
        (playlist_id, youtube_playlist_item_id) unique key.

        Existing rows are updated in place so that re-running sync never
        creates duplicate `PlaylistItem` rows. This constraint deliberately
        excludes `video_id`, so a video appearing twice in the same playlist
        is stored (and returned) as two distinct rows.

        Args:
            playlist_id: ID of the owning playlist.
            youtube_playlist_item_id: YouTube's playlist item ID.
            **fields: Column values to set (e.g. video_id, title,
                channel_title, position, availability, published_at, added_at).

        Returns:
            The inserted or updated playlist item.
        """
        logger.debug(
            "Upserting playlist item (playlist_id=%s, youtube_playlist_item_id=%s)",
            playlist_id, youtube_playlist_item_id,
        )
        item = self.get_item_by_youtube_id(playlist_id, youtube_playlist_item_id)
        if item is None:
            item = PlaylistItem(
                playlist_id=playlist_id,
                youtube_playlist_item_id=youtube_playlist_item_id,
                **fields,
            )
            self.db.add(item)
        else:
            for key, value in fields.items():
                setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        logger.debug("Upserted playlist item with id: %s", item.id)
        return item

    def count_duplicate_video_ids(self, playlist_id: str) -> int:
        """
        Count distinct video_ids that appear more than once in a playlist.

        Args:
            playlist_id: ID of the owning playlist.

        Returns:
            Number of distinct video_id values with more than one
            `PlaylistItem` row.
        """
        logger.debug("Counting duplicate video_ids (playlist_id=%s)", playlist_id)
        duplicated_video_ids = (
            select(PlaylistItem.video_id)
            .where(PlaylistItem.playlist_id == playlist_id)
            .group_by(PlaylistItem.video_id)
            .having(func.count() > 1)
        ).subquery()
        stmt = select(func.count()).select_from(duplicated_video_ids)
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Duplicate video_id count: %d", count)
        return count

    def count_unavailable_items(self, playlist_id: str) -> int:
        """
        Count a playlist's items whose availability is not "available".

        Args:
            playlist_id: ID of the owning playlist.

        Returns:
            Count of matching playlist items.
        """
        logger.debug("Counting unavailable items (playlist_id=%s)", playlist_id)
        stmt = (
            select(func.count())
            .select_from(PlaylistItem)
            .where(
                PlaylistItem.playlist_id == playlist_id,
                PlaylistItem.availability != "available",
            )
        )
        result = self.db.execute(stmt).scalar()
        count = result or 0
        logger.debug("Unavailable item count: %d", count)
        return count
