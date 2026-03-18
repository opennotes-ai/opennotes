from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any
from uuid import UUID

from src.simulation.memory.message_utils import (
    strip_orphaned_tool_messages,
    validate_tool_pairs,
)

logger = logging.getLogger(__name__)


def is_corrupted_history(history: list[dict[str, Any]]) -> bool:
    return not validate_tool_pairs(history)


def repair_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return strip_orphaned_tool_messages(history)


def repair_histories(
    histories: list[list[dict[str, Any]]],
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    scanned = 0
    corrupted = 0
    messages_stripped = 0

    for history in histories:
        scanned += 1
        if not is_corrupted_history(history):
            continue

        corrupted += 1
        repaired = repair_history(history)
        stripped_count = len(history) - len(repaired)
        messages_stripped += stripped_count

        if not dry_run:
            history[:] = repaired

    return {
        "scanned": scanned,
        "corrupted": corrupted,
        "messages_stripped": messages_stripped,
    }


async def repair_community_memories(
    community_server_id: UUID,
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    from src.database import get_session_maker  # noqa: PLC0415
    from src.simulation.models import (  # noqa: PLC0415
        SimAgentInstance,
        SimAgentMemory,
        SimulationRun,
    )

    scanned = 0
    corrupted = 0
    messages_stripped = 0

    async with get_session_maker()() as session:
        stmt = (
            select(SimAgentMemory)
            .join(SimAgentInstance, SimAgentMemory.agent_instance_id == SimAgentInstance.id)
            .join(SimulationRun, SimAgentInstance.simulation_run_id == SimulationRun.id)
            .where(SimulationRun.community_server_id == community_server_id)
            .options(joinedload(SimAgentMemory.agent_instance))
        )
        result = await session.execute(stmt)
        memories = result.scalars().all()

        for memory in memories:
            scanned += 1
            history = memory.message_history

            if not is_corrupted_history(history):
                continue

            corrupted += 1
            repaired = repair_history(history)
            stripped_count = len(history) - len(repaired)
            messages_stripped += stripped_count

            if not dry_run:
                memory.message_history = repaired
                logger.info(
                    "Repaired memory %s: stripped %d orphaned messages",
                    memory.id,
                    stripped_count,
                )

        if not dry_run:
            await session.commit()

    stats = {
        "scanned": scanned,
        "corrupted": corrupted,
        "messages_stripped": messages_stripped,
    }

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info(
        "[%s] Repair complete: scanned=%d, corrupted=%d, messages_stripped=%d",
        mode,
        scanned,
        corrupted,
        messages_stripped,
    )

    return stats


def main() -> None:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Repair corrupted SimAgentMemory message histories"
    )
    parser.add_argument(
        "community_server_id",
        type=UUID,
        help="UUID of the community server to scan",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Apply repairs (default is dry-run)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dry_run = not args.live
    if dry_run:
        logger.info("Running in DRY RUN mode (use --live to apply changes)")
    else:
        logger.warning("Running in LIVE mode — changes will be committed")

    stats = asyncio.run(repair_community_memories(args.community_server_id, dry_run=dry_run))

    print("\nResults:")
    print(f"  Memories scanned:    {stats['scanned']}")
    print(f"  Corrupted found:     {stats['corrupted']}")
    print(f"  Messages stripped:   {stats['messages_stripped']}")

    if dry_run and stats["corrupted"] > 0:
        print("\nRe-run with --live to apply repairs.")

    sys.exit(0 if stats["corrupted"] == 0 else 1)


if __name__ == "__main__":
    main()
