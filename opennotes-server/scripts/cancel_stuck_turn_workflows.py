#!/usr/bin/env python3
"""Cancel stuck old-generation run_agent_turn workflows.

Identifies PENDING/ENQUEUED turn workflows whose generation is older than
the current generation of their simulation run, and cancels them.

Usage:
    cd opennotes/opennotes-server
    uv run python scripts/cancel_stuck_turn_workflows.py --dry-run
    uv run python scripts/cancel_stuck_turn_workflows.py --execute
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dbos import DBOS
from sqlalchemy import select

from src.config import get_settings
from src.database import get_session_maker, init_db
from src.dbos_workflows.config import destroy_dbos, get_dbos
from src.simulation.models import SimAgentInstance, SimulationRun

GEN_PATTERN = re.compile(r"-gen(\d+)-")


async def main(dry_run: bool) -> None:
    get_settings()
    await init_db()

    dbos = get_dbos()
    DBOS.listen_queues([])
    dbos.launch()

    found = 0
    cancelled = 0

    async with get_session_maker()() as session:
        runs_result = await session.execute(
            select(SimulationRun.id, SimulationRun.generation, SimulationRun.status).where(
                SimulationRun.status.in_(["running", "paused"])
            )
        )
        runs = runs_result.all()

        if not runs:
            print("No running or paused simulation runs found.")
            return

        print(f"Found {len(runs)} active simulation run(s)\n")

        for run_id, current_gen, status in runs:
            print(f"Run {run_id} (status={status}, generation={current_gen})")

            agents_result = await session.execute(
                select(SimAgentInstance.id).where(SimAgentInstance.simulation_run_id == run_id)
            )
            agent_ids = [str(row[0]) for row in agents_result.all()]

            if not agent_ids:
                print("  No agent instances found.\n")
                continue

            print(f"  Checking {len(agent_ids)} agent(s)...")

            for agent_id in agent_ids:
                workflows = await asyncio.to_thread(
                    DBOS.list_workflows,
                    workflow_id_prefix=f"turn-{agent_id}-",
                    status=["ENQUEUED", "PENDING"],
                    load_input=False,
                    load_output=False,
                )

                for wf in workflows:
                    match = GEN_PATTERN.search(wf.workflow_id)
                    if not match:
                        continue
                    wf_gen = int(match.group(1))
                    if wf_gen >= current_gen:
                        continue

                    found += 1
                    age_str = ""
                    if wf.created_at:
                        import pendulum

                        created = pendulum.from_timestamp(wf.created_at / 1000)
                        age_str = f", age={pendulum.now('UTC').diff(created).in_words()}"

                    prefix = "[DRY RUN] " if dry_run else ""
                    print(
                        f"  {prefix}Cancel: {wf.workflow_id} "
                        f"(gen{wf_gen} < current gen{current_gen}, "
                        f"status={wf.status}{age_str})"
                    )

                    if not dry_run:
                        try:
                            await asyncio.to_thread(DBOS.cancel_workflow, wf.workflow_id)
                            cancelled += 1
                        except Exception as e:
                            print(f"  ERROR: Failed to cancel {wf.workflow_id}: {e}")

            print()

    print("=" * 60)
    if dry_run:
        print(f"Would cancel: {found} workflow(s)")
    else:
        print(f"Cancelled: {cancelled} workflow(s)")

    destroy_dbos()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cancel stuck old-generation run_agent_turn workflows"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
