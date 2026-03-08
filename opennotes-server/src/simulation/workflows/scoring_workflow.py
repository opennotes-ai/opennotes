from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from dbos import DBOS, Queue

from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)

community_scoring_queue = Queue(
    name="community_scoring",
    concurrency=3,
)


@DBOS.workflow()
def score_community_server(community_server_id: str) -> dict[str, Any]:
    result = run_community_scoring_step(community_server_id)
    logger.info(
        "Community server scoring workflow completed",
        extra={
            "community_server_id": community_server_id,
            "total_scores_computed": result.get("total_scores_computed", 0),
        },
    )
    return result


@DBOS.step(
    retries_allowed=True,
    max_attempts=5,
    interval_seconds=5.0,
    backoff_rate=2.0,
)
def run_community_scoring_step(community_server_id: str) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.simulation.scoring_integration import score_community_server_notes

    async def _score() -> dict[str, Any]:
        async with get_session_maker()() as session:
            result = await score_community_server_notes(UUID(community_server_id), session)
            return {
                "community_server_id": str(result.community_server_id),
                "unscored_notes_processed": result.unscored_notes_processed,
                "rescored_notes_processed": result.rescored_notes_processed,
                "total_scores_computed": result.total_scores_computed,
                "tier_name": result.tier_name,
                "scorer_type": result.scorer_type,
            }

    return run_sync(_score())


SCORE_COMMUNITY_SERVER_WORKFLOW_NAME: str = score_community_server.__qualname__


async def dispatch_community_scoring(community_server_id: UUID) -> str:
    import asyncio

    from dbos import SetWorkflowID

    wf_id = f"score-community-{community_server_id}-{int(time.time())}"

    def _enqueue() -> str:
        with SetWorkflowID(wf_id):
            handle = community_scoring_queue.enqueue(
                score_community_server,
                str(community_server_id),
            )
            return handle.get_workflow_id()

    workflow_id = await asyncio.to_thread(_enqueue)

    logger.info(
        "Community scoring workflow dispatched",
        extra={
            "community_server_id": str(community_server_id),
            "workflow_id": workflow_id,
        },
    )
    return workflow_id
