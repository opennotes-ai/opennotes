#!/usr/bin/env python3
"""
Cleanup script for message_archive entries that should have been filtered.

Finds archives with short content (<10 chars) or low similarity scores (<0.6)
that were created by system requests, and cascade soft-deletes them.

Usage:
    uv run python scripts/cleanup_bad_archives.py              # dry run
    uv run python scripts/cleanup_bad_archives.py --execute    # apply changes
    uv run python scripts/cleanup_bad_archives.py --min-length 15  # custom threshold
"""

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_session_maker
from src.notes.message_archive_models import MessageArchive
from src.notes.models import Note, Request


async def find_bad_archives(
    db: AsyncSession,
    min_content_length: int = 10,
    max_similarity_score: float = 0.6,
) -> list[dict]:
    stmt = (
        select(
            MessageArchive.id,
            MessageArchive.content_text,
            Request.request_id,
            Request.requested_by,
            Request.similarity_score,
            Request.note_id,
        )
        .join(Request, Request.message_archive_id == MessageArchive.id)
        .where(
            MessageArchive.deleted_at.is_(None),
            Request.deleted_at.is_(None),
            Request.requested_by.like("system-%"),
            or_(
                and_(
                    MessageArchive.content_text.isnot(None),
                    func.length(MessageArchive.content_text) < min_content_length,
                ),
                and_(
                    Request.similarity_score.isnot(None),
                    Request.similarity_score < max_similarity_score,
                ),
            ),
        )
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "archive_id": row.id,
            "content_text": row.content_text,
            "request_id": row.request_id,
            "requested_by": row.requested_by,
            "similarity_score": row.similarity_score,
            "note_id": row.note_id,
        }
        for row in rows
    ]


def _resolve_note_action(note: Note | None) -> tuple[bool, bool, str | None]:
    if note is None:
        return False, True, None
    if not note.ai_generated:
        return False, False, "human_note"
    if len(note.ratings) > 0:
        return False, False, "rated_ai_note"
    return True, True, None


async def cascade_soft_delete_archive(
    db: AsyncSession,
    archive_id: UUID,
    *,
    execute: bool = False,
) -> dict:
    archive = (
        await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
    ).scalar_one_or_none()

    if not archive:
        return {"archive_id": str(archive_id), "error": "not_found"}

    result = {
        "archive_id": str(archive_id),
        "content_preview": (archive.content_text or "")[:50],
        "archive_deleted": False,
        "request_deleted": False,
        "note_deleted": False,
        "skipped_reason": None,
    }

    if archive.deleted_at is None:
        result["archive_deleted"] = True
        if execute:
            archive.soft_delete()

    request = (
        await db.execute(select(Request).where(Request.message_archive_id == archive_id))
    ).scalar_one_or_none()

    if not request:
        return result

    result["request_id"] = request.request_id

    if not request.requested_by.startswith("system-"):
        result["skipped_reason"] = "non_system_request"
        return result

    if request.note_id is None:
        result["request_deleted"] = True
        if execute:
            request.soft_delete()
        return result

    note = (
        await db.execute(
            select(Note).where(Note.id == request.note_id).options(selectinload(Note.ratings))
        )
    ).scalar_one_or_none()

    result["note_id"] = str(note.id) if note else None
    note_deleted, request_deleted, skipped_reason = _resolve_note_action(note)
    result["note_deleted"] = note_deleted
    result["request_deleted"] = request_deleted
    result["skipped_reason"] = skipped_reason

    if execute and (note_deleted or request_deleted):
        if note_deleted and note is not None:
            note.soft_delete()
        if request_deleted:
            request.soft_delete()

    return result


async def run_cleanup(args: argparse.Namespace) -> None:
    mode_label = "(DRY RUN)" if not args.execute else "(EXECUTING)"
    print(f"{'=' * 60}")
    print(f"Archive Cleanup {mode_label}")
    print(f"Min content length: {args.min_length}")
    print(f"Max similarity score: {args.max_score}")
    print(f"{'=' * 60}\n")

    async with get_session_maker()() as db:
        bad_archives = await find_bad_archives(
            db,
            min_content_length=args.min_length,
            max_similarity_score=args.max_score,
        )

        print(f"Found {len(bad_archives)} candidate archives\n")

        if not bad_archives:
            print("Nothing to clean up.")
            return

        stats = {
            "archives_deleted": 0,
            "requests_deleted": 0,
            "notes_deleted": 0,
            "skipped_non_system_request": 0,
            "skipped_human_note": 0,
            "skipped_rated_ai_note": 0,
        }

        for entry in bad_archives:
            result = await cascade_soft_delete_archive(
                db, entry["archive_id"], execute=args.execute
            )

            content_preview = (entry["content_text"] or "")[:30]
            score = entry["similarity_score"]
            print(
                f"  Archive {result['archive_id'][:8]}... content='{content_preview}' score={score}"
            )

            if result["archive_deleted"]:
                stats["archives_deleted"] += 1
                print("    -> archive: DELETED")
            if result["request_deleted"]:
                stats["requests_deleted"] += 1
                print(f"    -> request {result.get('request_id', '?')}: DELETED")
            if result["note_deleted"]:
                stats["notes_deleted"] += 1
                note_id_short = str(result.get("note_id", "?"))[:8]
                print(f"    -> note {note_id_short}...: DELETED")
            if result["skipped_reason"]:
                key = f"skipped_{result['skipped_reason']}"
                stats[key] = stats.get(key, 0) + 1
                print(f"    -> skipped: {result['skipped_reason']}")

        if args.execute:
            await db.commit()
            print("\nChanges committed.")
        else:
            print("\nDRY RUN - no changes made. Use --execute to apply.")

        print("\nSummary:")
        print(f"  Archives deleted: {stats['archives_deleted']}")
        print(f"  Requests deleted: {stats['requests_deleted']}")
        print(f"  Notes deleted: {stats['notes_deleted']}")
        print(f"  Skipped (non-system request): {stats['skipped_non_system_request']}")
        print(f"  Skipped (human note): {stats['skipped_human_note']}")
        print(f"  Skipped (rated AI note): {stats['skipped_rated_ai_note']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup bad message archives")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually apply changes (default: dry run)",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=10,
        help="Minimum content length threshold (default: 10)",
    )
    parser.add_argument(
        "--max-score",
        type=float,
        default=0.6,
        help="Maximum similarity score threshold (default: 0.6)",
    )
    args = parser.parse_args()
    asyncio.run(run_cleanup(args))


if __name__ == "__main__":
    main()
