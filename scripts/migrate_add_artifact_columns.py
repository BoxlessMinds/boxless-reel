#!/usr/bin/env python3
"""
Migration script to add artifact-provenance columns to the documents table.

Adds `source`, `source_message_id`, and `source_block_index` to an
already-existing `documents` table (create_all()/Document.__table__.create()
only creates missing tables, it will not add columns to one that already
exists - hence this ad-hoc ALTER TABLE script, following the same pattern
as scripts/migrate_add_documents.py).

Safe to re-run: columns already present are skipped.

IMPORTANT: back up the database before running this against real data.
See CLAUDE.md "Docker Database Backup" for the exact steps:

    docker ps --filter "ancestor=transcript-api" --format "{{.Names}}"
    mkdir -p BACKUP
    docker cp <container_name>:/app/transcripts.db ./BACKUP/transcripts_backup_$(date +%Y%m%d_%H%M%S).db
    sqlite3 ./BACKUP/transcripts_backup_*.db "PRAGMA integrity_check;"

Usage:
    # From project root:
    uv run python scripts/migrate_add_artifact_columns.py

    # Or in Docker:
    docker exec boxless-api python scripts/migrate_add_artifact_columns.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from src.database import engine
from src.models import Document  # noqa: F401 - import to register the model

NEW_COLUMNS = {
    "source": "ALTER TABLE documents ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'upload'",
    "source_message_id": "ALTER TABLE documents ADD COLUMN source_message_id VARCHAR(36)",
    "source_block_index": "ALTER TABLE documents ADD COLUMN source_block_index INTEGER",
}


def get_existing_columns() -> set[str]:
    """Get the set of existing column names on the documents table."""
    inspector = inspect(engine)
    return {col["name"] for col in inspector.get_columns("documents")}


def main() -> None:
    print("=" * 60)
    print("Artifact Columns Migration Script")
    print("=" * 60)
    print(
        "\n[!] Make sure you have backed up transcripts.db per CLAUDE.md "
        "before continuing.\n"
    )

    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        print("[FAILED] 'documents' table does not exist. Run migrate_add_documents.py first.")
        sys.exit(1)

    existing = get_existing_columns()
    print(f"Existing 'documents' columns ({len(existing)}): {sorted(existing)}")

    with engine.begin() as conn:
        for column_name, ddl in NEW_COLUMNS.items():
            if column_name in existing:
                print(f"[OK] Column '{column_name}' already exists. Skipping.")
                continue
            print(f"[...] Adding column '{column_name}'...")
            conn.execute(text(ddl))
            print(f"[OK] Added column '{column_name}'.")

        print("[...] Ensuring index on 'source_message_id'...")
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_documents_source_message_id "
                "ON documents(source_message_id)"
            )
        )
        print("[OK] Index ensured.")

    final_columns = get_existing_columns()
    print(f"\nFinal 'documents' columns ({len(final_columns)}): {sorted(final_columns)}")

    print("\n" + "=" * 60)
    print("Migration complete! Your existing data is safe.")
    print("=" * 60)


if __name__ == "__main__":
    main()
