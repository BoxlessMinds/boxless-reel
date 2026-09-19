"""Tests for WatchHistoryService's Takeout watch-history.json parsing.

Per the data-layer contract,
`WatchHistoryEntry.video_id` is nullable: ad/unparseable Takeout rows are
still persisted with `video_id=None` so `entry_count` matches Takeout's own
row count. A row is only dropped outright when it's structurally unusable
(not a dict, or missing/unparseable `title`/`time`, both NOT NULL columns).
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.services.watch_history_service import (
    ParsedWatchHistoryRow,
    WatchHistoryService,
)


@pytest.fixture
def watch_history_service(tmp_path: Path) -> WatchHistoryService:
    repository = MagicMock()
    return WatchHistoryService(repository, storage_path=tmp_path)


VALID_ROW = {
    "header": "YouTube",
    "title": "Watched Some Cool Video",
    "titleUrl": "https://www.youtube.com/watch?v=abc123XYZ_9",
    "time": "2024-01-15T12:34:56.000Z",
}

AD_ROW_NO_TITLE_URL = {
    "header": "YouTube",
    "title": "Watched a video that has been removed",
    "time": "2024-01-16T09:00:00.000Z",
}

MALFORMED_URL_ROW = {
    "header": "YouTube",
    "title": "Watched something weird",
    "titleUrl": "https://www.youtube.com/not-a-video-url",
    "time": "2024-01-17T09:00:00.000Z",
}

MISSING_TIME_ROW = {
    "header": "YouTube",
    "title": "Watched Another Video",
    "titleUrl": "https://www.youtube.com/watch?v=def456UVW_8",
}

MISSING_TITLE_ROW = {
    "header": "YouTube",
    "titleUrl": "https://www.youtube.com/watch?v=def456UVW_8",
    "time": "2024-01-18T09:00:00.000Z",
}


class TestParseEntry:
    def test_valid_row_parses_with_video_id(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        entry = watch_history_service._parse_entry(VALID_ROW)

        assert entry is not None
        assert entry.video_id == "abc123XYZ_9"
        assert entry.watched_at == datetime(2024, 1, 15, 12, 34, 56)
        assert entry.title == "Watched Some Cool Video"

    def test_ad_row_without_title_url_is_still_stored_with_null_video_id(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        entry = watch_history_service._parse_entry(AD_ROW_NO_TITLE_URL)

        assert entry is not None
        assert entry.video_id is None
        assert entry.title == "Watched a video that has been removed"

    def test_malformed_title_url_is_stored_with_null_video_id(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        entry = watch_history_service._parse_entry(MALFORMED_URL_ROW)

        assert entry is not None
        assert entry.video_id is None

    def test_missing_time_is_dropped(self, watch_history_service: WatchHistoryService) -> None:
        assert watch_history_service._parse_entry(MISSING_TIME_ROW) is None

    def test_missing_title_is_dropped(self, watch_history_service: WatchHistoryService) -> None:
        assert watch_history_service._parse_entry(MISSING_TITLE_ROW) is None

    def test_non_dict_row_is_dropped(self, watch_history_service: WatchHistoryService) -> None:
        assert watch_history_service._parse_entry("not a dict") is None
        assert watch_history_service._parse_entry(None) is None

    def test_raw_video_id_url_variants_parse(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        row = {**VALID_ROW, "titleUrl": "https://youtu.be/shortIdShrt"}
        entry = watch_history_service._parse_entry(row)
        assert entry is not None
        assert entry.video_id == "shortIdShrt"

    def test_timestamp_normalized_to_naive_utc(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        entry = watch_history_service._parse_entry(VALID_ROW)
        assert entry is not None
        assert entry.watched_at.tzinfo is None


class TestParseEntries:
    def test_all_valid_rows_counts_match(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        rows = [VALID_ROW, {**VALID_ROW, "titleUrl": "https://youtu.be/anotherId12"}]

        entries, skipped_count = watch_history_service._parse_entries(rows)

        assert len(entries) == 2
        assert skipped_count == 0
        assert all(isinstance(e, ParsedWatchHistoryRow) for e in entries)
        assert all(e.video_id is not None for e in entries)

    def test_mixed_valid_ad_and_dropped_rows_does_not_fail_whole_import(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        rows = [
            VALID_ROW,
            AD_ROW_NO_TITLE_URL,
            MALFORMED_URL_ROW,
            MISSING_TIME_ROW,
            MISSING_TITLE_ROW,
        ]

        entries, skipped_count = watch_history_service._parse_entries(rows)

        # VALID_ROW, AD_ROW_NO_TITLE_URL, MALFORMED_URL_ROW are all storable
        # (title+time present); only the two rows missing title/time are
        # structurally dropped.
        assert len(entries) == 3
        assert skipped_count == 2
        video_ids = [e.video_id for e in entries]
        assert video_ids.count(None) == 2
        assert "abc123XYZ_9" in video_ids

    def test_empty_list_produces_no_entries_no_error(
        self, watch_history_service: WatchHistoryService
    ) -> None:
        entries, skipped_count = watch_history_service._parse_entries([])

        assert entries == []
        assert skipped_count == 0


class TestStreamToFile:
    async def test_streams_full_content_to_disk(
        self, watch_history_service: WatchHistoryService, tmp_path: Path
    ) -> None:
        content = b'[{"title": "x"}]'
        upload = MagicMock()

        async def fake_read(size: int) -> bytes:
            nonlocal content
            chunk, content = content[:size], content[size:]
            return chunk

        upload.read.side_effect = fake_read
        destination = tmp_path / "upload.json"

        total = await watch_history_service._stream_to_file(upload, destination, max_size=1024)

        assert total == len(b'[{"title": "x"}]')
        assert destination.read_bytes() == b'[{"title": "x"}]'

    async def test_raises_and_cleans_up_when_too_large(
        self, watch_history_service: WatchHistoryService, tmp_path: Path
    ) -> None:
        from src.services.watch_history_service import TakeoutFileTooLargeError

        content = b"x" * 100
        upload = MagicMock()

        async def fake_read(size: int) -> bytes:
            nonlocal content
            chunk, content = content[:size], content[size:]
            return chunk

        upload.read.side_effect = fake_read
        destination = tmp_path / "upload.json"

        with pytest.raises(TakeoutFileTooLargeError):
            await watch_history_service._stream_to_file(upload, destination, max_size=10)

        assert not destination.exists()


class TestImportWatchHistory:
    """End-to-end import_watch_history() against the WatchHistoryRepository contract."""

    @pytest.fixture
    def repository(self) -> MagicMock:
        from src.repositories.watch_history_repository import WatchHistoryRepository

        repo = MagicMock(spec=WatchHistoryRepository)
        repo.create_import.side_effect = lambda record: record
        return repo

    @pytest.fixture
    def service(self, repository: MagicMock, tmp_path: Path) -> WatchHistoryService:
        return WatchHistoryService(repository, storage_path=tmp_path)

    @staticmethod
    def _upload_for(content: bytes, filename: str = "watch-history.json") -> MagicMock:
        upload = MagicMock()
        upload.filename = filename

        async def fake_read(size: int) -> bytes:
            nonlocal content
            chunk, content = content[:size], content[size:]
            return chunk

        upload.read.side_effect = fake_read
        return upload

    async def test_all_valid_rows_reports_correct_entry_count(
        self, service: WatchHistoryService, repository: MagicMock
    ) -> None:
        import json

        rows = [VALID_ROW, {**VALID_ROW, "titleUrl": "https://youtu.be/anotherId12"}]
        upload = self._upload_for(json.dumps(rows).encode("utf-8"))

        import_record = await service.import_watch_history(upload, user_id="user-1")

        assert import_record.entry_count == 2
        assert import_record.status == "completed"
        repository.create_entries.assert_called_once()
        created_entries = repository.create_entries.call_args.args[0]
        assert len(created_entries) == 2

    async def test_mixed_rows_succeeds_with_partial_entry_count(
        self, service: WatchHistoryService, repository: MagicMock
    ) -> None:
        import json

        rows = [VALID_ROW, AD_ROW_NO_TITLE_URL, MISSING_TIME_ROW]
        upload = self._upload_for(json.dumps(rows).encode("utf-8"))

        import_record = await service.import_watch_history(upload, user_id="user-1")

        # VALID_ROW + AD_ROW_NO_TITLE_URL are storable; MISSING_TIME_ROW is dropped.
        assert import_record.entry_count == 2
        assert import_record.status == "completed"

    async def test_garbage_file_raises_clean_error_without_creating_import(
        self, service: WatchHistoryService, repository: MagicMock
    ) -> None:
        from src.services.watch_history_service import InvalidTakeoutFileError

        upload = self._upload_for(b"not json at all {{{")

        with pytest.raises(InvalidTakeoutFileError):
            await service.import_watch_history(upload, user_id="user-1")

        repository.create_import.assert_not_called()
        repository.create_entries.assert_not_called()

    async def test_empty_file_raises_clean_error(
        self, service: WatchHistoryService, repository: MagicMock
    ) -> None:
        from src.services.watch_history_service import InvalidTakeoutFileError

        upload = self._upload_for(b"")

        with pytest.raises(InvalidTakeoutFileError):
            await service.import_watch_history(upload, user_id="user-1")

        repository.create_import.assert_not_called()

    async def test_json_object_instead_of_array_raises_clean_error(
        self, service: WatchHistoryService, repository: MagicMock
    ) -> None:
        from src.services.watch_history_service import InvalidTakeoutFileError

        upload = self._upload_for(b'{"not": "an array"}')

        with pytest.raises(InvalidTakeoutFileError):
            await service.import_watch_history(upload, user_id="user-1")

        repository.create_import.assert_not_called()


class TestListImports:
    def test_returns_imports_and_total_from_repository(self) -> None:
        repository = MagicMock()
        repository.list_imports.return_value = ["import-1", "import-2"]
        repository.count_imports.return_value = 2
        service = WatchHistoryService(repository, storage_path=Path("."))

        imports, total = service.list_imports(user_id="user-1", skip=0, limit=20)

        assert imports == ["import-1", "import-2"]
        assert total == 2
        repository.list_imports.assert_called_once_with("user-1", skip=0, limit=20)
        repository.count_imports.assert_called_once_with("user-1")
