#!/usr/bin/env python3
"""
Migration script to add the documents table.

This script safely adds the documents table without affecting existing data.
SQLAlchemy's create_all() only creates tables that don't exist - it does NOT
drop, modify, or truncate existing tables.

Usage:
    # From project root:
    uv run python scripts/migrate_add_documents.py

    # Or in Docker:
    docker exec boxless-api python scripts/migrate_add_documents.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from src.database import Base, engine
from src.models import Document  # Import to register the model


def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def get_existing_tables() -> list[str]:
    """Get list of all existing tables."""
    inspector = inspect(engine)
    return inspector.get_table_names()


def main():
    print("=" * 60)
    print("Document Upload Migration Script")
    print("=" * 60)

    # Show existing tables
    existing_tables = get_existing_tables()
    print(f"\nExisting tables ({len(existing_tables)}):")
    for table in sorted(existing_tables):
        print(f"  - {table}")

    # Check if documents table already exists
    if check_table_exists("documents"):
        print("\n[OK] 'documents' table already exists. No migration needed.")
        return

    print("\n[...] 'documents' table does not exist. Creating...")

    # Create only the documents table (create_all is safe - only creates missing tables)
    # This will NOT modify or drop any existing tables
    Document.__table__.create(engine, checkfirst=True)

    # Verify creation
    if check_table_exists("documents"):
        print("[OK] 'documents' table created successfully!")

        # Show table structure
        inspector = inspect(engine)
        columns = inspector.get_columns("documents")
        print("\nTable structure:")
        for col in columns:
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            print(f"  - {col['name']}: {col['type']} {nullable}")
    else:
        print("[FAILED] Failed to create 'documents' table!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Migration complete! Your existing data is safe.")
    print("=" * 60)


if __name__ == "__main__":
    main()
