"""Pydantic schemas for watch-history import request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchHistoryImportResponse(BaseModel):
    """A single Google Takeout watch-history import record."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique identifier (UUID)")
    user_id: str = Field(description="Owning user's ID")
    original_filename: str = Field(description="Filename of the uploaded Takeout export")
    status: str = Field(description="Import status (e.g. 'completed', 'failed')")
    entry_count: int = Field(description="Number of successfully parsed watch-history entries")
    imported_at: datetime = Field(description="When this import completed")
    created_at: datetime = Field(description="When this import record was created")


class WatchHistoryImportListResponse(BaseModel):
    """Paginated list of past watch-history imports."""

    items: list[WatchHistoryImportResponse] = Field(description="List of watch-history imports")
    total: int = Field(description="Total number of imports")
    skip: int = Field(default=0, description="Number of records skipped")
    limit: int = Field(default=20, description="Maximum records returned")
