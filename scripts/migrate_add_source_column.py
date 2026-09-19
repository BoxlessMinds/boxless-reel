#!/usr/bin/env python3
"""
Migration script to add the 'source' column to the transcripts table.

This column tracks whether a transcript came from YouTube captions or
Whisper audio transcription. Existing rows default to 'captions'.

Usage:
    # From project root:
    uv run python scripts/migrate_add_source_column.py

    # Or in Docker:
    docker exec boxless-api python scripts/migrate_add_source_column.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from src.database import engine


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def main():
    print("=" * 60)
    print("Migration: Add 'source' column to transcripts table")
    print("=" * 60)

    if column_exists("transcripts", "source"):
        print("\n[OK] 'source' column already exists. No migration needed.")
        return

    print("\n[...] Adding 'source' column to 'transcripts' table...")

    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE transcripts ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'captions'")
        )

    # Verify
    if column_exists("transcripts", "source"):
        print("[OK] 'source' column added successfully!")
        print("     All existing transcripts defaulted to source='captions'.")
    else:
        print("[FAILED] Failed to add 'source' column!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Migration complete! Your existing data is safe.")
    print("=" * 60)


if __name__ == "__main__":
    main()
