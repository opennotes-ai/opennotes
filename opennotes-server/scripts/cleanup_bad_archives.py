#!/usr/bin/env python3
"""
Cleanup script for message_archive entries that should have been filtered.

Finds archives with short content (<10 chars) or low similarity scores (<0.6)
that were created by system requests, and cascade soft-deletes them.

Usage:
    # Local (uses app Settings / .env):
    uv run python scripts/cleanup_bad_archives.py

    # Production (uses ~/.pgpass for auth):
    uv run python scripts/cleanup_bad_archives.py --use-pgpass --dbhost <cloud-sql-host>
    uv run python scripts/cleanup_bad_archives.py --use-pgpass --dbhost <host> --dbname postgres --execute
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

FIND_BAD_ARCHIVES_SQL = text("""
    SELECT
        ma.id AS archive_id,
        ma.content_text,
        r.id AS request_pk,
        r.request_id,
        r.requested_by,
        r.similarity_score,
        r.note_id
    FROM message_archive ma
    JOIN requests r ON r.message_archive_id = ma.id
    WHERE ma.deleted_at IS NULL
      AND r.deleted_at IS NULL
      AND r.requested_by LIKE 'system-%'
      AND (
          (ma.content_text IS NOT NULL AND length(ma.content_text) < :min_length)
          OR (r.similarity_score IS NOT NULL AND r.similarity_score < :max_score)
      )
""")

SOFT_DELETE_SQL = text("""
    UPDATE {table} SET deleted_at = :now WHERE id = :id AND deleted_at IS NULL
""")

NOTE_INFO_SQL = text("""
    SELECT n.id, n.ai_generated,
           (SELECT count(*) FROM ratings nr WHERE nr.note_id = n.id) AS rating_count
    FROM notes n
    WHERE n.id = :note_id AND n.deleted_at IS NULL
""")


def _parse_pgpass(host: str, port: int = 5432, dbname: str = "opennotes") -> str:
    pgpass_path = Path.home() / ".pgpass"
    if not pgpass_path.exists():
        print(f"ERROR: {pgpass_path} not found", file=sys.stderr)
        sys.exit(1)

    for raw_line in pgpass_path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(":")
        if len(parts) != 5:
            continue
        pg_host, pg_port, pg_db, pg_user, pg_pass = parts
        host_match = pg_host in ("*", host)
        port_match = pg_port in ("*", str(port))
        db_match = pg_db in ("*", dbname)
        if host_match and port_match and db_match:
            return f"postgresql+asyncpg://{pg_user}:{pg_pass}@{host}:{port}/{dbname}"

    print(f"ERROR: No matching entry in {pgpass_path} for {host}:{port}/{dbname}", file=sys.stderr)
    print("\nAvailable entries:", file=sys.stderr)
    for raw_line in pgpass_path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(":")
        if len(parts) == 5:
            print(f"  {parts[0]}:{parts[1]}/{parts[2]} (user: {parts[3]})", file=sys.stderr)
    sys.exit(1)


def _make_session(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, echo=False, future=True, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _soft_delete(db: AsyncSession, table: str, record_id: Any, *, execute: bool) -> bool:
    if execute:
        stmt = text(f"UPDATE {table} SET deleted_at = :now WHERE id = :id AND deleted_at IS NULL")
        result = await db.execute(stmt, {"now": datetime.now(UTC), "id": record_id})
        return result.rowcount > 0  # type: ignore[union-attr]
    return True


async def cascade_soft_delete(
    db: AsyncSession,
    entry: dict,
    *,
    execute: bool = False,
) -> dict:
    result: dict[str, Any] = {
        "archive_id": str(entry["archive_id"]),
        "content_preview": (entry["content_text"] or "")[:50],
        "archive_deleted": False,
        "request_deleted": False,
        "note_deleted": False,
        "skipped_reason": None,
    }

    result["archive_deleted"] = True
    await _soft_delete(db, "message_archive", entry["archive_id"], execute=execute)

    result["request_id"] = entry["request_id"]

    if not entry["requested_by"].startswith("system-"):
        result["skipped_reason"] = "non_system_request"
        return result

    if entry["note_id"] is None:
        result["request_deleted"] = True
        await _soft_delete(db, "requests", entry["request_pk"], execute=execute)
        return result

    note_row = (await db.execute(NOTE_INFO_SQL, {"note_id": entry["note_id"]})).first()

    if note_row is None:
        result["request_deleted"] = True
        await _soft_delete(db, "requests", entry["request_pk"], execute=execute)
        return result

    result["note_id"] = str(note_row.id)

    if not note_row.ai_generated:
        result["skipped_reason"] = "human_note"
        return result
    if note_row.rating_count > 0:
        result["skipped_reason"] = "rated_ai_note"
        return result

    result["note_deleted"] = True
    result["request_deleted"] = True
    await _soft_delete(db, "notes", note_row.id, execute=execute)
    await _soft_delete(db, "requests", entry["request_pk"], execute=execute)
    return result


async def run_cleanup(args: argparse.Namespace) -> None:
    mode_label = "(DRY RUN)" if not args.execute else "(EXECUTING)"
    print(f"{'=' * 60}")
    print(f"Archive Cleanup {mode_label}")
    print(f"Min content length: {args.min_length}")
    print(f"Max similarity score: {args.max_score}")

    if args.use_pgpass:
        database_url = _parse_pgpass(args.dbhost, args.dbport, args.dbname)
        session_maker = _make_session(database_url)
        print(f"Database: {args.dbhost}:{args.dbport}/{args.dbname} (via pgpass)")
    else:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.database import get_session_maker

        session_maker = get_session_maker()
        print("Database: using app Settings (.env)")

    print(f"{'=' * 60}\n")

    async with session_maker() as db:
        rows = await db.execute(
            FIND_BAD_ARCHIVES_SQL,
            {"min_length": args.min_length, "max_score": args.max_score},
        )
        bad_archives = [row._asdict() for row in rows.all()]

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
            result = await cascade_soft_delete(db, entry, execute=args.execute)

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
    parser.add_argument(
        "--use-pgpass",
        action="store_true",
        help="Read credentials from ~/.pgpass instead of app Settings",
    )
    parser.add_argument(
        "--dbhost",
        type=str,
        default="localhost",
        help="Database host (used with --use-pgpass, default: localhost)",
    )
    parser.add_argument(
        "--dbport",
        type=int,
        default=5432,
        help="Database port (used with --use-pgpass, default: 5432)",
    )
    parser.add_argument(
        "--dbname",
        type=str,
        default="opennotes",
        help="Database name (used with --use-pgpass, default: opennotes)",
    )
    args = parser.parse_args()
    asyncio.run(run_cleanup(args))


if __name__ == "__main__":
    main()
