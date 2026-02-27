from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from dbos import DBOS

from src.utils.async_compat import run_sync

logger = logging.getLogger(__name__)


@DBOS.workflow()
def score_community_server(community_server_id: str) -> dict[str, Any]:
    """DBOS workflow for manual community server scoring.

    Wraps score_community_server_notes as a DBOS step for durable execution.
    """
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
    """Dispatch community server scoring via DBOSClient.enqueue()."""
    import asyncio

    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    wf_id = f"score-community-{community_server_id}"
    options: EnqueueOptions = {
        "queue_name": "community_scoring",
        "workflow_name": SCORE_COMMUNITY_SERVER_WORKFLOW_NAME,
        "workflow_id": wf_id,
        "deduplication_id": wf_id,
    }
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        str(community_server_id),
    )

    logger.info(
        "Community scoring workflow dispatched",
        extra={
            "community_server_id": str(community_server_id),
            "workflow_id": handle.workflow_id,
        },
    )
    return handle.workflow_id
