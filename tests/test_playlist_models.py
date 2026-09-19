"""Tests for Playlist, PlaylistItem, and QuotaLedgerEntry models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.playlist import Playlist, PlaylistItem, QuotaLedgerEntry


def _make_playlist(db, user_id, youtube_playlist_id="PL_test_001"):
    """Create and persist a Playlist record."""
    playlist = Playlist(
        id=str(uuid4()),
        user_id=user_id,
        youtube_playlist_id=youtube_playlist_id,
        title="Test Playlist",
        description="A playlist used for testing.",
        privacy_status="private",
        item_count=0,
        is_owned=True,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


class TestPlaylistCreation:
    """Tests for Playlist model creation and defaults."""

    def test_create_with_all_fields(self, test_db, test_user):
        """Playlist can be created with explicit values for all columns."""
        playlist = _make_playlist(test_db, test_user.id)
        assert playlist.id is not None
        assert playlist.user_id == test_user.id
        assert playlist.youtube_playlist_id == "PL_test_001"
        assert playlist.title == "Test Playlist"
        assert playlist.privacy_status == "private"
        assert playlist.item_count == 0
        assert playlist.is_owned is True
        assert isinstance(playlist.created_at, datetime)
        assert isinstance(playlist.updated_at, datetime)

    def test_uuid_auto_generated(self, test_db, test_user):
        """When id is not provided, a UUID is automatically generated."""
        playlist = Playlist(
            user_id=test_user.id,
            youtube_playlist_id="PL_test_auto",
            title="Auto ID Playlist",
            privacy_status="public",
            last_synced_at=datetime.now(timezone.utc),
        )
        test_db.add(playlist)
        test_db.commit()
        test_db.refresh(playlist)
        assert playlist.id is not None
        assert len(playlist.id) == 36


class TestPlaylistUniqueConstraint:
    """Tests for the (user_id, youtube_playlist_id) unique constraint."""

    def test_duplicate_youtube_playlist_id_for_same_user_rejected(
        self, test_db, test_user
    ):
        """Two Playlist rows with the same (user_id, youtube_playlist_id) raise IntegrityError."""
        _make_playlist(test_db, test_user.id, youtube_playlist_id="PL_dup")
        duplicate = Playlist(
            user_id=test_user.id,
            youtube_playlist_id="PL_dup",
            title="Duplicate Playlist",
            privacy_status="private",
            last_synced_at=datetime.now(timezone.utc),
        )
        test_db.add(duplicate)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_same_youtube_playlist_id_for_different_users_allowed(
        self, test_db, test_user, test_admin
    ):
        """The same youtube_playlist_id may exist for two different users."""
        p1 = _make_playlist(test_db, test_user.id, youtube_playlist_id="PL_shared")
        p2 = _make_playlist(test_db, test_admin.id, youtube_playlist_id="PL_shared")
        assert p1.id != p2.id
        assert p1.youtube_playlist_id == p2.youtube_playlist_id


class TestPlaylistItemCreation:
    """Tests for PlaylistItem model creation and defaults."""

    def test_create_with_all_fields(self, test_db, test_user):
        """PlaylistItem can be created with explicit values for all columns."""
        playlist = _make_playlist(test_db, test_user.id)
        item = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_001",
            video_id="video00001a",
            title="Test Video",
            channel_title="Test Channel",
            position=0,
            availability="available",
            published_at=datetime.now(timezone.utc),
            added_at=datetime.now(timezone.utc),
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)
        assert item.id is not None
        assert item.playlist_id == playlist.id
        assert item.video_id == "video00001a"
        assert item.availability == "available"
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    def test_availability_defaults_to_unknown(self, test_db, test_user):
        """availability defaults to 'unknown' when not specified."""
        playlist = _make_playlist(test_db, test_user.id)
        item = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_default",
            video_id="video00002b",
            position=1,
        )
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)
        assert item.availability == "unknown"


class TestPlaylistItemUniqueConstraint:
    """Tests for the (playlist_id, youtube_playlist_item_id) unique constraint (AC3/AC4)."""

    def test_duplicate_youtube_playlist_item_id_rejected(self, test_db, test_user):
        """Two PlaylistItem rows with the same (playlist_id, youtube_playlist_item_id) raise IntegrityError."""
        playlist = _make_playlist(test_db, test_user.id)
        item1 = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_dup",
            video_id="video00003c",
            position=0,
        )
        test_db.add(item1)
        test_db.commit()

        item2 = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_dup",
            video_id="video00004d",
            position=1,
        )
        test_db.add(item2)
        with pytest.raises(IntegrityError):
            test_db.commit()
        test_db.rollback()

    def test_same_video_id_twice_in_playlist_allowed(self, test_db, test_user):
        """AC4: a playlist with the same video appearing twice is stored as two distinct rows.

        The unique constraint is on (playlist_id, youtube_playlist_item_id) only,
        never on (playlist_id, video_id) — proving dedupe will have
        something to act on.
        """
        playlist = _make_playlist(test_db, test_user.id)
        item1 = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_first_occurrence",
            video_id="video00005e",
            position=0,
        )
        item2 = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_second_occurrence",
            video_id="video00005e",
            position=5,
        )
        test_db.add_all([item1, item2])
        test_db.commit()
        test_db.refresh(item1)
        test_db.refresh(item2)

        assert item1.id != item2.id
        assert item1.video_id == item2.video_id == "video00005e"
        assert item1.youtube_playlist_item_id != item2.youtube_playlist_item_id


class TestPlaylistItemCascadeDelete:
    """Tests for cascade delete from Playlist to PlaylistItem."""

    def test_deleting_playlist_cascades_to_items(self, test_db, test_user):
        """Deleting a Playlist removes its PlaylistItem rows."""
        playlist = _make_playlist(test_db, test_user.id)
        item = PlaylistItem(
            playlist_id=playlist.id,
            youtube_playlist_item_id="PLI_cascade",
            video_id="video00006f",
            position=0,
        )
        test_db.add(item)
        test_db.commit()
        item_id = item.id
        playlist_id = playlist.id

        test_db.delete(playlist)
        test_db.commit()

        assert test_db.get(Playlist, playlist_id) is None
        assert test_db.get(PlaylistItem, item_id) is None


class TestQuotaLedgerEntryCreation:
    """Tests for the minimal QuotaLedgerEntry model."""

    def test_create_with_all_fields(self, test_db, test_user):
        """QuotaLedgerEntry can be created and persisted."""
        entry = QuotaLedgerEntry(
            user_id=test_user.id,
            endpoint="playlists.list",
            units=1,
        )
        test_db.add(entry)
        test_db.commit()
        test_db.refresh(entry)
        assert entry.id is not None
        assert entry.user_id == test_user.id
        assert entry.endpoint == "playlists.list"
        assert entry.units == 1
        assert isinstance(entry.created_at, datetime)

    def test_uuid_auto_generated(self, test_db, test_user):
        """When id is not provided, a UUID is automatically generated."""
        entry = QuotaLedgerEntry(
            user_id=test_user.id,
            endpoint="playlistItems.list",
            units=1,
        )
        test_db.add(entry)
        test_db.commit()
        test_db.refresh(entry)
        assert entry.id is not None
        assert len(entry.id) == 36
