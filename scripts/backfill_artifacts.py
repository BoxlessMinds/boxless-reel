#!/usr/bin/env python3
"""
Backfill script: save artifacts from past chat messages into the document
library.

Scans every assistant message in every (regular, non-cross-chat) session,
re-runs the same artifact detection used for live auto-save
(src.utils.artifact_parser), and creates a Document for each promoted
artifact that doesn't already have one. Idempotent via
DocumentRepository.get_by_source() - safe to re-run, and safe to run
even after live auto-save (AgentService.query) has already started saving
new messages, since already-saved artifacts are detected and skipped.

Cross-chat sessions are out of scope: CrossChatMessage has no direct
session a Document can attach to (see the project's implementation plan).

IMPORTANT: back up the database before running with --apply. See
CLAUDE.md "Docker Database Backup" for the exact steps:

    docker ps --filter "ancestor=transcript-api" --format "{{.Names}}"
    mkdir -p BACKUP
    docker cp <container_name>:/app/transcripts.db ./BACKUP/transcripts_backup_$(date +%Y%m%d_%H%M%S).db
    sqlite3 ./BACKUP/transcripts_backup_*.db "PRAGMA integrity_check;"

Usage:
    # Report only, no writes (default):
    uv run python scripts/backfill_artifacts.py

    # Test against a backed-up copy first:
    DATABASE_URL=sqlite:///./BACKUP/transcripts_backup_XXXX.db \
        uv run python scripts/backfill_artifacts.py --dry-run

    # Actually create documents:
    uv run python scripts/backfill_artifacts.py --apply
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

# Export API keys to os.environ for libraries that read directly from the
# environment (e.g., LanceDB's OpenAI embeddings). Normally done by
# src.main at app startup - this script never imports src.main, so it
# needs the same bridge (see src/main.py for the canonical version).
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

from sqlalchemy import select

from src.database import SessionLocal
from src.models.session import Message
from src.services import get_document_service
from src.utils.artifact_parser import parse_artifacts


@dataclass
class BackfillSummary:
    """Outcome counters for a backfill run."""

    messages_scanned: int = 0
    artifacts_found: int = 0
    documents_created: int = 0
    documents_already_existed: int = 0
    errors: list[str] = field(default_factory=list)


def run_backfill(db, *, dry_run: bool, document_service=None) -> BackfillSummary:
    """
    Scan all assistant messages and save their promoted artifacts.

    Args:
        db: SQLAlchemy database session.
        dry_run: If True, report what would happen without writing anything.
        document_service: DocumentService to use. Defaults to
            get_document_service(db) - overridable for testing.

    Returns:
        Summary of what was scanned/created/skipped/errored.
    """
    summary = BackfillSummary()
    if document_service is None:
        document_service = get_document_service(db)

    messages = db.execute(
        select(Message).where(Message.role == "assistant")
    ).scalars().all()

    for message in messages:
        summary.messages_scanned += 1
        session = message.session
        if session is None:
            summary.errors.append(f"message {message.id}: no session found")
            continue

        artifacts = parse_artifacts(message.content)
        for block_index, artifact in enumerate(artifacts):
            summary.artifacts_found += 1

            existing = document_service.repository.get_by_source(
                session.id, message.id, block_index
            )
            if existing is not None:
                summary.documents_already_existed += 1
                continue

            if dry_run:
                print(
                    f"[would create] session={session.id} message={message.id} "
                    f"block={block_index} kind={artifact.kind!r} title={artifact.title!r}"
                )
                summary.documents_created += 1
                continue

            try:
                document_service.save_artifact_document(
                    artifact=artifact,
                    session_id=session.id,
                    user_id=session.user_id,
                    source_message_id=message.id,
                    source_block_index=block_index,
                )
                summary.documents_created += 1
                print(
                    f"[created] session={session.id} message={message.id} "
                    f"block={block_index} title={artifact.title!r}"
                )
            except Exception as e:  # noqa: BLE001 - one bad artifact must not abort the run
                error = f"message {message.id} block {block_index}: {e}"
                summary.errors.append(error)
                print(f"[error] {error}")

    return summary


def main() -> None:
    # Titles pulled from real message content can contain characters
    # outside the default Windows console codepage (e.g. emoji).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create documents. Without this flag, the script only reports.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit alias for the default (no-write) behavior.",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    print("=" * 60)
    print("Artifact Backfill Script")
    print("=" * 60)
    print(
        "\n[!] Make sure you have backed up transcripts.db per CLAUDE.md "
        "before running with --apply.\n"
    )
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'APPLY (writing documents)'}")
    print("Scope: regular chat sessions only (cross-chat excluded)\n")

    db = SessionLocal()
    try:
        summary = run_backfill(db, dry_run=dry_run)
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Messages scanned:          {summary.messages_scanned}")
    print(f"Artifacts found:           {summary.artifacts_found}")
    print(f"Documents created:         {summary.documents_created}")
    print(f"Documents already existed: {summary.documents_already_existed}")
    print(f"Errors:                    {len(summary.errors)}")
    for error in summary.errors:
        print(f"  - {error}")

    if dry_run:
        print("\nThis was a dry run - no documents were created. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
