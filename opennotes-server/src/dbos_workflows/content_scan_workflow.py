"""DBOS workflow for content scan pipeline.

Replaces the TaskIQ-based content monitoring tasks with durable DBOS execution.
The orchestration workflow receives signals from NATS handlers as batches arrive,
tracks scan state as workflow variables, and runs finalization when complete.

Architecture:
    NATS Handler                    DBOS Orchestrator             DBOS Batch Worker
        |                                |                              |
        | BulkScanMessageBatchEvent      |                              |
        | ----> enqueue batch workflow --+----> (queued)                |
        |                                |       process_batch -------> |
        |                                |       <-- send batch_complete|
        |                                |                              |
        | AllBatchesTransmittedEvent     |                              |
        | ----> send all_transmitted --> |                              |
        |                                | (check termination)          |
        |                                | finalize_scan_step           |

Per-strategy steps (task-1089):
    The batch processing is split into 4 DBOS steps with Redis-backed message
    passing between them:
    1. preprocess_batch_step - filters existing requests, builds context maps
    2. similarity_scan_step - runs similarity search, produces candidates
    3. flashpoint_scan_step - runs flashpoint detection, produces candidates
    4. relevance_filter_step - unified LLM filtering on all candidates

    Steps 2 and 3 are independent and could run in parallel once DBOS adds
    async workflow support. Currently they run sequentially because DBOS
    workflows in Python are synchronous (see DBOS_PARALLEL_NOTES below).

DBOS_PARALLEL_NOTES:
    DBOS Python workflows are synchronous functions decorated with @DBOS.workflow().
    Steps are synchronous functions decorated with @DBOS.step(). Each step is
    checkpointed for replay safety. Because workflows are sync, asyncio.gather
    cannot be used directly to parallelize step calls. Parallel step execution
    would require either:
    - DBOS async workflow support (not yet available in dbos-transact-py)
    - Child workflow pattern with separate queue workers
    - concurrent.futures with careful DBOS context propagation (untested)
    The current sequential execution is correct and the step decomposition
    enables future parallelism without structural changes.
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid as uuid_module
from typing import TYPE_CHECKING, Any
from uuid import UUID

import orjson
from dbos import DBOS, Queue, SetEnqueueOptions, SetWorkflowID

from src.bulk_content_scan.schemas import (
    BulkScanMessage,
    BulkScanStatus,
    ContentItem,
)
from src.dbos_workflows.enqueue_utils import safe_enqueue
from src.dbos_workflows.token_bucket.config import WorkflowWeight
from src.dbos_workflows.token_bucket.gate import TokenGate
from src.monitoring import get_logger
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


def _deserialize_to_bulk_scan_message(msg_data: dict) -> BulkScanMessage:
    """Deserialize a Redis message dict to BulkScanMessage, handling both formats.

    During rollout, Redis may contain either ContentItem format (with content_id)
    written by the updated NATS handler, or legacy BulkScanMessage format (with
    message_id) written before the migration. Both are supported transparently.
    """
    if "content_id" in msg_data:
        content_item = ContentItem.model_validate(msg_data)
        return BulkScanMessage(
            message_id=content_item.content_id,
            channel_id=content_item.channel_id,
            community_server_id=content_item.community_server_id,
            content=content_item.content_text,
            author_id=content_item.author_id,
            author_username=content_item.author_username,
            timestamp=content_item.timestamp,
            attachment_urls=content_item.attachment_urls,
            embed_content=content_item.platform_metadata.get("embed_content"),
        )
    return BulkScanMessage.model_validate(msg_data)


REDIS_BATCH_TTL_SECONDS = 86400
REDIS_REPLAY_TTL_SECONDS = 7 * 24 * 3600

content_scan_queue = Queue(
    name="content_scan",
    worker_concurrency=6,
    concurrency=12,
)

BATCH_RECV_TIMEOUT_SECONDS = 600
POST_ALL_TRANSMITTED_TIMEOUT_SECONDS = 60
SCAN_RECV_TIMEOUT_SECONDS = 30
ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS = 1800
ADAPTIVE_TIMEOUT_SECONDS_PER_MESSAGE = 5
ADAPTIVE_TIMEOUT_MIN_SECONDS = 120


def compute_adaptive_timeout_cap(messages_scanned: int) -> float:
    cap = max(ADAPTIVE_TIMEOUT_MIN_SECONDS, messages_scanned * ADAPTIVE_TIMEOUT_SECONDS_PER_MESSAGE)
    return min(float(cap), float(ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS))


def get_batch_redis_key(scan_id: str, batch_number: int, suffix: str) -> str:
    from src.config import get_settings

    env = get_settings().ENVIRONMENT
    return f"{env}:bulk_scan:{suffix}:{scan_id}:{batch_number}"


def get_scan_finalizing_redis_key(scan_id: str) -> str:
    from src.config import get_settings

    env = get_settings().ENVIRONMENT
    return f"{env}:bulk_scan:finalizing:{scan_id}"


def _build_suppressed_batch_result(
    *,
    batch_number: int,
    skipped_count: int = 0,
    error_count: int = 0,
    step_errors: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "processed": 0,
        "skipped": skipped_count,
        "errors": error_count,
        "flagged_count": 0,
        "batch_number": batch_number,
    }
    if step_errors:
        result["step_errors"] = step_errors
    return result


async def store_messages_in_redis(
    redis_client: Redis,
    key: str,
    messages: list[dict[str, Any]],
    ttl: int = REDIS_BATCH_TTL_SECONDS,
) -> str:
    await redis_client.setex(key, ttl, orjson.dumps(messages))
    return key


async def load_messages_from_redis(
    redis_client: Redis,
    key: str,
) -> list[dict[str, Any]]:
    data = await redis_client.get(key)
    if data is None:
        raise ValueError(f"Redis key {key} not found or expired")
    await redis_client.expire(key, REDIS_REPLAY_TTL_SECONDS)
    return orjson.loads(data)


@DBOS.step()
def _checkpoint_wall_clock_step() -> float:
    """Return time.time() as a DBOS-checkpointed value.

    Using time.time() (wall-clock) instead of time.monotonic()
    ensures the recorded start time is meaningful across process restarts
    during DBOS replay.
    """
    return time.time()


async def _scan_is_terminal_async(session: Any, scan_id: UUID) -> bool:
    from sqlalchemy import select

    from src.bulk_content_scan.models import BulkContentScanLog

    result = await session.execute(
        select(BulkContentScanLog.status).where(BulkContentScanLog.id == scan_id)
    )
    status = result.scalar_one_or_none()
    if inspect.isawaitable(status):
        status = await status
    return status in {BulkScanStatus.COMPLETED, BulkScanStatus.FAILED}


async def _scan_is_finalizing_async(redis_client: Redis, scan_id: str) -> bool:
    exists_result = redis_client.exists(get_scan_finalizing_redis_key(scan_id))
    if inspect.isawaitable(exists_result):
        exists_result = await exists_result
    if isinstance(exists_result, bool):
        return exists_result
    if isinstance(exists_result, int):
        return exists_result > 0
    return False


async def _scan_is_inactive_async(session: Any, redis_client: Redis, scan_uuid: UUID) -> bool:
    return await _scan_is_terminal_async(session, scan_uuid) or await _scan_is_finalizing_async(
        redis_client, str(scan_uuid)
    )


async def _skip_step_persist_if_scan_terminal(
    session: Any,
    redis_client: Redis,
    scan_uuid: UUID,
    *,
    step_name: str,
    scan_id: str,
    batch_number: int,
) -> bool:
    if not await _scan_is_inactive_async(session, redis_client, scan_uuid):
        return False

    logger.info(
        "%s step finished after scan became terminal/finalizing; skipping late persistence",
        step_name,
        extra={"scan_id": scan_id, "batch_number": batch_number},
    )
    return True


@DBOS.workflow()
def content_scan_orchestration_workflow(  # noqa: PLR0912
    scan_id: str,
    community_server_id: str,
    scan_types_json: str,
) -> dict[str, Any]:
    """DBOS orchestration workflow for content scan pipeline.

    This workflow:
    1. Creates the scan record in the database (step)
    2. Loops receiving signals as batches complete
    3. When all batches processed and transmission complete, runs finalization

    Signals received:
    - "batch_complete": {processed, skipped, errors, flagged_count, batch_number}
    - "all_transmitted": {messages_scanned}

    Args:
        scan_id: UUID string of the scan (also used as workflow ID for idempotency)
        community_server_id: UUID string of the community server
        scan_types_json: JSON-encoded list of scan type strings

    Returns:
        dict with scan results summary
    """
    gate = TokenGate(pool="default", weight=WorkflowWeight.CONTENT_SCAN)
    gate.acquire()
    try:
        workflow_id = DBOS.workflow_id

        logger.info(
            "Starting content scan orchestration workflow",
            extra={
                "workflow_id": workflow_id,
                "scan_id": scan_id,
                "community_server_id": community_server_id,
            },
        )

        create_scan_record_step(scan_id, community_server_id)

        processed_count = 0
        skipped_count = 0
        error_count = 0
        flagged_count = 0
        all_transmitted = False
        all_transmitted_at: float | None = None
        messages_scanned = 0
        batches_completed = 0
        wall_clock_start = _checkpoint_wall_clock_step()

        tx_signal = DBOS.recv("all_transmitted", timeout_seconds=SCAN_RECV_TIMEOUT_SECONDS)
        if tx_signal is not None:
            all_transmitted = True
            all_transmitted_at = time.time()
            messages_scanned = tx_signal.get("messages_scanned", 0)
            logger.info(
                "Orchestrator received all_transmitted",
                extra={
                    "scan_id": scan_id,
                    "messages_scanned": messages_scanned,
                },
            )
            if messages_scanned == 0:
                logger.info(
                    "Zero-message scan, skipping to finalization",
                    extra={"scan_id": scan_id},
                )

        if not (all_transmitted and messages_scanned == 0):
            while True:
                elapsed = time.time() - wall_clock_start
                if elapsed >= ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS:
                    logger.warning(
                        "Orchestrator exceeded maximum wall-clock timeout, aborting",
                        extra={
                            "scan_id": scan_id,
                            "elapsed_seconds": elapsed,
                            "max_seconds": ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS,
                            "processed_count": processed_count,
                            "skipped_count": skipped_count,
                            "error_count": error_count,
                            "batches_completed": batches_completed,
                        },
                    )
                    break

                if not all_transmitted and batches_completed > 0:
                    tx_signal = DBOS.recv("all_transmitted", timeout_seconds=0)
                    if tx_signal is not None:
                        all_transmitted = True
                        all_transmitted_at = time.time()
                        messages_scanned = tx_signal.get("messages_scanned", 0)
                        logger.info(
                            "Orchestrator received all_transmitted",
                            extra={
                                "scan_id": scan_id,
                                "messages_scanned": messages_scanned,
                            },
                        )

                total_accounted = processed_count + skipped_count + error_count
                if all_transmitted and total_accounted >= messages_scanned:
                    if total_accounted > messages_scanned:
                        logger.warning(
                            "Overcounting detected: accounted total exceeds messages_scanned",
                            extra={
                                "scan_id": scan_id,
                                "total_accounted": total_accounted,
                                "messages_scanned": messages_scanned,
                            },
                        )
                    logger.info(
                        "All batches processed, proceeding to finalization",
                        extra={
                            "scan_id": scan_id,
                            "processed_count": processed_count,
                            "skipped_count": skipped_count,
                            "error_count": error_count,
                            "messages_scanned": messages_scanned,
                        },
                    )
                    break

                waiting_for_first_batch = not all_transmitted and batches_completed == 0
                if waiting_for_first_batch:
                    tx_signal = DBOS.recv(
                        "all_transmitted",
                        timeout_seconds=POST_ALL_TRANSMITTED_TIMEOUT_SECONDS,
                    )
                    if tx_signal is not None:
                        all_transmitted = True
                        all_transmitted_at = time.time()
                        messages_scanned = tx_signal.get("messages_scanned", 0)
                        logger.info(
                            "Orchestrator received all_transmitted",
                            extra={
                                "scan_id": scan_id,
                                "messages_scanned": messages_scanned,
                            },
                        )
                        if messages_scanned == 0:
                            logger.info(
                                "Late zero-message scan, skipping to finalization",
                                extra={"scan_id": scan_id},
                            )
                            break
                        continue

                batch_timeout = (
                    POST_ALL_TRANSMITTED_TIMEOUT_SECONDS
                    if all_transmitted
                    else BATCH_RECV_TIMEOUT_SECONDS
                )
                batch_result = DBOS.recv("batch_complete", timeout_seconds=batch_timeout)

                if batch_result is not None:
                    processed_count += batch_result.get("processed", 0)
                    skipped_count += batch_result.get("skipped", 0)
                    error_count += batch_result.get("errors", 0)
                    flagged_count += batch_result.get("flagged_count", 0)
                    batches_completed += 1

                    logger.info(
                        "Orchestrator received batch_complete",
                        extra={
                            "scan_id": scan_id,
                            "batches_completed": batches_completed,
                            "processed_count": processed_count,
                            "skipped_count": skipped_count,
                            "error_count": error_count,
                        },
                    )
                    continue

                if waiting_for_first_batch:
                    logger.warning(
                        "Orchestrator timed out waiting for initial all_transmitted or first batch_complete",
                        extra={
                            "scan_id": scan_id,
                            "processed_count": processed_count,
                            "all_transmitted": all_transmitted,
                            "timeout_seconds": POST_ALL_TRANSMITTED_TIMEOUT_SECONDS,
                        },
                    )
                    break

                if not all_transmitted:
                    logger.warning(
                        "Orchestrator timed out waiting for batch_complete",
                        extra={
                            "scan_id": scan_id,
                            "processed_count": processed_count,
                            "all_transmitted": all_transmitted,
                            "timeout_seconds": batch_timeout,
                        },
                    )
                    break

                adaptive_cap = compute_adaptive_timeout_cap(messages_scanned)
                time_since_tx = time.time() - (all_transmitted_at or wall_clock_start)
                if time_since_tx >= adaptive_cap:
                    logger.warning(
                        "Orchestrator exceeded adaptive timeout cap after all_transmitted",
                        extra={
                            "scan_id": scan_id,
                            "messages_scanned": messages_scanned,
                            "processed_count": processed_count,
                            "skipped_count": skipped_count,
                            "error_count": error_count,
                            "actual_total": processed_count + skipped_count + error_count,
                            "missing_count": messages_scanned
                            - (processed_count + skipped_count + error_count),
                            "adaptive_cap_seconds": adaptive_cap,
                            "time_since_all_transmitted_seconds": time_since_tx,
                        },
                    )
                    break

                logger.info(
                    "Post-all_transmitted batch_complete recv timed out, continuing to poll",
                    extra={
                        "scan_id": scan_id,
                        "messages_scanned": messages_scanned,
                        "actual_total": processed_count + skipped_count + error_count,
                        "time_since_all_transmitted_seconds": time_since_tx,
                        "adaptive_cap_seconds": adaptive_cap,
                    },
                )
                continue

        mark_scan_finalizing_step(scan_id=scan_id)

        try:
            result = finalize_scan_step(
                scan_id=scan_id,
                community_server_id=community_server_id,
                messages_scanned=messages_scanned,
                processed_count=processed_count,
                skipped_count=skipped_count,
                error_count=error_count,
                flagged_count=flagged_count,
                all_transmitted_observed=all_transmitted,
                finalization_incomplete=all_transmitted
                and (processed_count + skipped_count + error_count) < messages_scanned,
            )
        except Exception:
            try:
                clear_scan_finalizing_step(scan_id=scan_id)
            except Exception:
                logger.warning(
                    "Failed to clear finalizing latch after finalization error",
                    extra={"scan_id": scan_id},
                    exc_info=True,
                )
            raise

        try:
            clear_scan_finalizing_step(scan_id=scan_id)
        except Exception:
            logger.warning(
                "Failed to clear finalizing latch after successful finalization",
                extra={"scan_id": scan_id},
                exc_info=True,
            )

        logger.info(
            "Content scan orchestration workflow completed",
            extra={
                "workflow_id": workflow_id,
                "scan_id": scan_id,
                "result": result,
            },
        )

        return result
    finally:
        gate.release()


@DBOS.step()
def create_scan_record_step(scan_id: str, community_server_id: str) -> bool:
    """Create or update the scan record to IN_PROGRESS status.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server

    Returns:
        True if successful
    """
    from src.bulk_content_scan.models import BulkContentScanLog
    from src.bulk_content_scan.schemas import BulkScanStatus
    from src.database import get_session_maker

    scan_uuid = UUID(scan_id)

    async def _update_scan_status() -> bool:
        from sqlalchemy import select

        async with get_session_maker()() as session:
            stmt = (
                select(BulkContentScanLog)
                .where(BulkContentScanLog.id == scan_uuid)
                .with_for_update()
            )
            result = await session.execute(stmt)
            scan_log = result.scalar_one_or_none()

            if scan_log and scan_log.status == BulkScanStatus.PENDING:
                scan_log.status = BulkScanStatus.IN_PROGRESS
                await session.commit()

            return True

    return run_sync(_update_scan_status())


@DBOS.step()
def get_scan_terminal_state_step(scan_id: str) -> bool:
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker

    scan_uuid = UUID(scan_id)
    settings = get_settings()

    async def _load_state() -> bool:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        async with get_session_maker()() as session:
            return await _scan_is_inactive_async(session, redis_conn, scan_uuid)

    return run_sync(_load_state())


@DBOS.step()
def mark_scan_finalizing_step(scan_id: str) -> bool:
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings

    settings = get_settings()

    async def _mark_finalizing() -> bool:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        await redis_conn.setex(
            get_scan_finalizing_redis_key(scan_id), REDIS_REPLAY_TTL_SECONDS, "1"
        )
        return True

    return run_sync(_mark_finalizing())


@DBOS.step()
def clear_scan_finalizing_step(scan_id: str) -> bool:
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings

    settings = get_settings()

    async def _clear_finalizing() -> bool:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        await redis_conn.delete(get_scan_finalizing_redis_key(scan_id))
        return True

    return run_sync(_clear_finalizing())


def _run_batch_scan_steps(
    *,
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    filtered_messages_key: str,
    context_maps_key: str,
    scan_types: list[str],
    step_errors: list[str],
) -> tuple[int, int]:
    similarity_result: dict[str, Any] = {
        "similarity_candidates_key": "",
        "candidate_count": 0,
    }
    flashpoint_result: dict[str, Any] = {
        "flashpoint_candidates_key": "",
        "candidate_count": 0,
    }

    if "similarity" in scan_types:
        try:
            similarity_result = similarity_scan_step(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                filtered_messages_key=filtered_messages_key,
                context_maps_key=context_maps_key,
            )
        except Exception as e:
            logger.error("similarity_scan_step failed", exc_info=True)
            step_errors.append(f"similarity: {e}")

    if "conversation_flashpoint" in scan_types:
        try:
            flashpoint_result = flashpoint_scan_step(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                filtered_messages_key=filtered_messages_key,
                context_maps_key=context_maps_key,
            )
        except Exception as e:
            logger.error("flashpoint_scan_step failed", exc_info=True)
            step_errors.append(f"flashpoint: {e}")

    try:
        filter_result = content_reviewer_step(
            scan_id=scan_id,
            community_server_id=community_server_id,
            batch_number=batch_number,
            similarity_candidates_key=similarity_result.get("similarity_candidates_key", ""),
            flashpoint_candidates_key=flashpoint_result.get("flashpoint_candidates_key", ""),
        )
        flagged_count = filter_result.get("flagged_count", 0)
        errors = filter_result.get("errors", 0) + len(step_errors)
        return flagged_count, errors
    except Exception as e:
        logger.error("content_reviewer_step failed", exc_info=True)
        step_errors.append(f"content_reviewer: {e}")
        return 0, len(step_errors)


@DBOS.workflow()
def process_content_scan_batch(
    orchestrator_workflow_id: str,
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    messages_redis_key: str,
    scan_types_json: str,
) -> dict[str, Any]:
    """DBOS queued workflow for processing a single content scan batch.

    Splits processing into 4 per-strategy DBOS steps with Redis-backed
    message passing:
    1. preprocess_batch_step - filters existing requests, builds context
    2. similarity_scan_step - runs similarity search
    3. flashpoint_scan_step - runs flashpoint detection
    4. relevance_filter_step - unified LLM relevance filtering

    Steps 2 and 3 are independent and run sequentially. See DBOS_PARALLEL_NOTES
    in module docstring for why they cannot yet run in parallel.

    Args:
        orchestrator_workflow_id: Workflow ID of the orchestrator to signal
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        messages_redis_key: Redis key where messages are stored
        scan_types_json: JSON-encoded list of scan type strings

    Returns:
        dict with batch processing results
    """
    logger.info(
        "Starting content scan batch processing (per-strategy steps)",
        extra={
            "scan_id": scan_id,
            "batch_number": batch_number,
            "orchestrator_workflow_id": orchestrator_workflow_id,
        },
    )

    scan_types = orjson.loads(scan_types_json)

    if get_scan_terminal_state_step(scan_id):
        logger.info(
            "Scan already terminal before batch execution",
            extra={"scan_id": scan_id, "batch_number": batch_number},
        )
        return {
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "flagged_count": 0,
            "batch_number": batch_number,
        }

    errors = 0
    flagged_count = 0
    message_count = 0
    skipped_count = 0
    step_errors: list[str] = []
    preprocess_result: dict[str, Any] | None = None

    try:
        preprocess_result = preprocess_batch_step(
            scan_id=scan_id,
            community_server_id=community_server_id,
            batch_number=batch_number,
            messages_redis_key=messages_redis_key,
            scan_types_json=scan_types_json,
        )
    except Exception as e:
        logger.error("preprocess_batch_step failed", exc_info=True)
        step_errors.append(f"preprocess: {e}")

    if preprocess_result is not None:
        message_count = preprocess_result.get("message_count", 0)
        skipped_count = preprocess_result.get("skipped_count", 0)

        if get_scan_terminal_state_step(scan_id):
            logger.info(
                "Scan became terminal after preprocess; skipping remaining batch stages",
                extra={"scan_id": scan_id, "batch_number": batch_number},
            )
            return _build_suppressed_batch_result(
                batch_number=batch_number,
                skipped_count=skipped_count,
                error_count=len(step_errors),
                step_errors=step_errors,
            )

        if message_count > 0:
            filtered_messages_key = preprocess_result["filtered_messages_key"]
            context_maps_key = preprocess_result.get("context_maps_key", "")
            flagged_count, errors = _run_batch_scan_steps(
                scan_id=scan_id,
                community_server_id=community_server_id,
                batch_number=batch_number,
                filtered_messages_key=filtered_messages_key,
                context_maps_key=context_maps_key,
                scan_types=scan_types,
                step_errors=step_errors,
            )
        else:
            errors = len(step_errors)
    else:
        errors = len(step_errors)

    result: dict[str, Any] = {
        "processed": message_count,
        "skipped": skipped_count,
        "errors": errors,
        "flagged_count": flagged_count,
        "batch_number": batch_number,
    }
    if step_errors:
        result["step_errors"] = step_errors

    if get_scan_terminal_state_step(scan_id):
        logger.info(
            "Scan became terminal/finalizing before batch_complete; suppressing late signal",
            extra={"scan_id": scan_id, "batch_number": batch_number},
        )
        return _build_suppressed_batch_result(
            batch_number=batch_number,
            skipped_count=skipped_count,
            error_count=errors,
            step_errors=step_errors,
        )

    DBOS.send(
        orchestrator_workflow_id,
        result,
        topic="batch_complete",
    )

    logger.info(
        "Batch processing complete, signal sent to orchestrator",
        extra={
            "scan_id": scan_id,
            "batch_number": batch_number,
            "processed": result.get("processed", 0),
            "flagged_count": result.get("flagged_count", 0),
            "step_errors": step_errors if step_errors else None,
        },
    )

    return result


@DBOS.step()
def process_batch_messages_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    messages_json: str,
    scan_types_json: str,
) -> dict[str, Any]:
    """Process a batch of messages through the content scan pipeline.

    This is a DBOS step wrapping the async BulkContentScanService calls.
    Non-deterministic operations (similarity search, LLM, flashpoint detection)
    are checkpointed by DBOS for durability.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        messages_json: JSON-encoded list of message dicts
        scan_types_json: JSON-encoded list of scan type strings

    Returns:
        dict with: processed, skipped, errors, flagged_count, batch_number
    """
    from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
    from src.bulk_content_scan.scan_types import ScanType
    from src.bulk_content_scan.schemas import BulkScanMessage
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)
    messages = orjson.loads(messages_json)
    scan_types = [ScanType(st) for st in orjson.loads(scan_types_json)]

    _diag = {"scan_id": scan_id, "batch_number": batch_number}

    try:
        loop = asyncio.get_running_loop()
        logger.info(
            "process_batch_messages_step: running event loop detected",
            extra={**_diag, "loop": str(loop)},
        )
    except RuntimeError:
        logger.info("process_batch_messages_step: no running event loop", extra=_diag)

    async def _process() -> dict[str, Any]:
        from sqlalchemy import select

        logger.info("_process: entered async function", extra=_diag)

        logger.info("_process: acquiring redis client", extra=_diag)
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        logger.info("_process: redis client acquired", extra=_diag)

        logger.info("_process: opening db session", extra=_diag)
        async with get_session_maker()() as session:
            logger.info("_process: db session opened, querying platform_id", extra=_diag)
            result = await session.execute(
                select(CommunityServer.platform_community_server_id).where(
                    CommunityServer.id == community_uuid
                )
            )
            platform_id = result.scalar_one_or_none()
            logger.info(
                "_process: platform_id query done", extra={**_diag, "platform_id": str(platform_id)}
            )

            if not platform_id:
                logger.error(
                    "Platform ID not found for community server",
                    extra={"community_server_id": community_server_id},
                )
                return {
                    "processed": 0,
                    "skipped": 0,
                    "errors": len(messages),
                    "flagged_count": 0,
                    "batch_number": batch_number,
                }

            logger.info("_process: initializing services", extra=_diag)
            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            flashpoint_service = get_flashpoint_service()
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
                flashpoint_service=flashpoint_service,
            )
            logger.info("_process: services initialized, starting process_messages", extra=_diag)

            typed_messages = [BulkScanMessage.model_validate(msg) for msg in messages]

            try:
                logger.info(
                    "_process: calling process_messages",
                    extra={
                        **_diag,
                        "message_count": len(typed_messages),
                        "scan_types": [str(st) for st in scan_types],
                    },
                )
                flagged = await service.process_messages(
                    scan_id=scan_uuid,
                    messages=typed_messages,
                    community_server_platform_id=platform_id,
                    scan_types=scan_types,
                )
                processed = len(typed_messages)
                errors = 0
                logger.info(
                    "_process: process_messages completed",
                    extra={**_diag, "processed": processed, "flagged_count": len(flagged)},
                )
            except Exception as e:
                flagged = []
                processed = 0
                errors = len(typed_messages)
                logger.warning(
                    "Error processing batch",
                    extra={
                        "scan_id": scan_id,
                        "batch_number": batch_number,
                        "error": str(e),
                    },
                )
                await service.record_error(
                    scan_id=scan_uuid,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    message_id=typed_messages[0].message_id if typed_messages else None,
                    batch_number=batch_number,
                )

            for msg in flagged:
                await service.append_flagged_result(scan_uuid, msg)

            return {
                "processed": processed,
                "skipped": 0,
                "errors": errors,
                "flagged_count": len(flagged),
                "batch_number": batch_number,
            }

    return run_sync(_process())


@DBOS.step()
def preprocess_batch_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    messages_redis_key: str,
    scan_types_json: str,
) -> dict[str, Any]:
    """Preprocess a batch: filter existing requests, build context maps.

    Reads messages from Redis, filters out messages that already have note
    requests, builds channel context maps for flashpoint detection, and
    stores filtered messages back in Redis.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        messages_redis_key: Redis key containing the raw messages
        scan_types_json: JSON-encoded list of scan type strings

    Returns:
        dict with: filtered_messages_key, context_maps_key, message_count,
                   skipped_count
    """
    from src.bulk_content_scan.scan_types import ScanType
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)
    scan_types = [ScanType(st) for st in orjson.loads(scan_types_json)]

    async def _preprocess() -> dict[str, Any]:
        from sqlalchemy import select

        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, messages_redis_key)
        typed_messages = [_deserialize_to_bulk_scan_message(msg) for msg in raw_messages]
        original_count = len(typed_messages)

        async with get_session_maker()() as session:
            result = await session.execute(
                select(CommunityServer.platform_community_server_id).where(
                    CommunityServer.id == community_uuid
                )
            )
            platform_id = result.scalar_one_or_none()

            if not platform_id:
                logger.error(
                    "Platform ID not found for preprocess step",
                    extra={"community_server_id": community_server_id},
                )
                return {
                    "filtered_messages_key": "",
                    "context_maps_key": "",
                    "message_count": 0,
                    "skipped_count": 0,
                }

            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
            )

            if await _scan_is_inactive_async(session, redis_conn, scan_uuid):
                logger.info(
                    "Preprocess step skipped because scan is already terminal/finalizing",
                    extra={"scan_id": scan_id, "batch_number": batch_number},
                )
                return {
                    "filtered_messages_key": "",
                    "context_maps_key": "",
                    "message_count": 0,
                    "skipped_count": 0,
                }

            platform_message_ids = [msg.message_id for msg in typed_messages]
            existing_ids = await service.get_existing_request_message_ids(platform_message_ids)
            skipped_count = 0

            if existing_ids:
                typed_messages = [
                    msg for msg in typed_messages if msg.message_id not in existing_ids
                ]
                skipped_count = original_count - len(typed_messages)
                logger.info(
                    "Preprocess: skipped messages with existing note requests",
                    extra={
                        "scan_id": scan_id,
                        "batch_number": batch_number,
                        "skipped_count": skipped_count,
                        "remaining_count": len(typed_messages),
                    },
                )

            needs_context = ScanType.CONVERSATION_FLASHPOINT in scan_types
            channel_context_map: dict[str, list[dict[str, Any]]] = {}
            if needs_context and typed_messages:
                raw_map = BulkContentScanService.build_channel_context_map(typed_messages)
                raw_map = await service._enrich_context_from_cache(raw_map, platform_id)
                channel_context_map = {
                    ch: [m.model_dump(mode="json") for m in msgs] for ch, msgs in raw_map.items()
                }
            if await _skip_step_persist_if_scan_terminal(
                session,
                redis_conn,
                scan_uuid,
                step_name="Preprocess",
                scan_id=scan_id,
                batch_number=batch_number,
            ):
                return {
                    "filtered_messages_key": "",
                    "context_maps_key": "",
                    "message_count": 0,
                    "skipped_count": 0,
                }

            if needs_context and typed_messages:
                await service._populate_cross_batch_cache(typed_messages, platform_id)

            if await _skip_step_persist_if_scan_terminal(
                session,
                redis_conn,
                scan_uuid,
                step_name="Preprocess",
                scan_id=scan_id,
                batch_number=batch_number,
            ):
                return {
                    "filtered_messages_key": "",
                    "context_maps_key": "",
                    "message_count": 0,
                    "skipped_count": 0,
                }

            filtered_key = get_batch_redis_key(scan_id, batch_number, "filtered")
            context_key = get_batch_redis_key(scan_id, batch_number, "context")

            filtered_dicts = [m.model_dump(mode="json") for m in typed_messages]
            await store_messages_in_redis(redis_conn, filtered_key, filtered_dicts)
            await store_messages_in_redis(redis_conn, context_key, [channel_context_map])

            return {
                "filtered_messages_key": filtered_key,
                "context_maps_key": context_key,
                "message_count": len(typed_messages),
                "skipped_count": skipped_count,
            }

    return run_sync(_preprocess())


@DBOS.step()
def similarity_scan_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    filtered_messages_key: str,
    context_maps_key: str,
) -> dict[str, Any]:
    """Run similarity scan on filtered messages and produce candidates.

    Reads filtered messages from Redis, runs similarity search on each,
    and stores candidates back in Redis.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        filtered_messages_key: Redis key with filtered messages
        context_maps_key: Redis key with context maps (unused by similarity)

    Returns:
        dict with: similarity_candidates_key, candidate_count
    """
    from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)

    async def _similarity_scan() -> dict[str, Any]:
        from sqlalchemy import select

        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, filtered_messages_key)
        typed_messages = [_deserialize_to_bulk_scan_message(msg) for msg in raw_messages]

        async with get_session_maker()() as session:
            result = await session.execute(
                select(CommunityServer.platform_community_server_id).where(
                    CommunityServer.id == community_uuid
                )
            )
            platform_id = result.scalar_one_or_none()

            if not platform_id:
                logger.error(
                    "Platform ID not found for similarity scan",
                    extra={"community_server_id": community_server_id},
                )
                return {"similarity_candidates_key": "", "candidate_count": 0}

            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            flashpoint_service = get_flashpoint_service()
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
                flashpoint_service=flashpoint_service,
            )

            if await _scan_is_inactive_async(session, redis_conn, scan_uuid):
                logger.info(
                    "Similarity step skipped because scan is already terminal/finalizing",
                    extra={"scan_id": scan_id, "batch_number": batch_number},
                )
                return {"similarity_candidates_key": "", "candidate_count": 0}

            candidates = []
            for msg in typed_messages:
                if not msg.content or len(msg.content.strip()) < 10:
                    continue
                candidate = await service._similarity_scan_candidate(scan_uuid, msg, platform_id)
                if candidate:
                    candidates.append(candidate)
            if await _skip_step_persist_if_scan_terminal(
                session,
                redis_conn,
                scan_uuid,
                step_name="Similarity",
                scan_id=scan_id,
                batch_number=batch_number,
            ):
                return {"similarity_candidates_key": "", "candidate_count": 0}

            candidates_key = get_batch_redis_key(scan_id, batch_number, "similarity_candidates")
            candidates_data = [c.model_dump(mode="json") for c in candidates]
            await store_messages_in_redis(redis_conn, candidates_key, candidates_data)

            logger.info(
                "Similarity scan step completed",
                extra={
                    "scan_id": scan_id,
                    "batch_number": batch_number,
                    "candidate_count": len(candidates),
                },
            )

            return {
                "similarity_candidates_key": candidates_key,
                "candidate_count": len(candidates),
            }

    return run_sync(_similarity_scan())


@DBOS.step()
def flashpoint_scan_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    filtered_messages_key: str,
    context_maps_key: str,
) -> dict[str, Any]:
    """Run flashpoint detection on filtered messages and produce candidates.

    Reads filtered messages and context maps from Redis, runs flashpoint
    detection on each message, and stores candidates back in Redis.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        filtered_messages_key: Redis key with filtered messages
        context_maps_key: Redis key with context maps

    Returns:
        dict with: flashpoint_candidates_key, candidate_count
    """
    from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService

    settings = get_settings()
    scan_uuid = UUID(scan_id)

    async def _flashpoint_scan() -> dict[str, Any]:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, filtered_messages_key)
        typed_messages = [_deserialize_to_bulk_scan_message(msg) for msg in raw_messages]

        max_msgs = settings.FLASHPOINT_MAX_BATCH_MESSAGES
        if len(typed_messages) > max_msgs:
            logger.warning(
                "Flashpoint batch exceeds cap, processing first %d of %d messages",
                max_msgs,
                len(typed_messages),
                extra={
                    "scan_id": scan_id,
                    "batch_number": batch_number,
                    "original_count": len(typed_messages),
                    "capped_count": max_msgs,
                },
            )
            typed_messages = typed_messages[:max_msgs]

        context_data = await load_messages_from_redis(redis_conn, context_maps_key)
        channel_context_raw: dict[str, list[dict[str, Any]]] = (
            context_data[0] if context_data else {}
        )
        channel_context_map: dict[str, list[BulkScanMessage]] = {}
        for ch_id, msg_dicts in channel_context_raw.items():
            channel_context_map[ch_id] = [_deserialize_to_bulk_scan_message(m) for m in msg_dicts]

        async with get_session_maker()() as session:
            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            flashpoint_service = get_flashpoint_service()
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
                flashpoint_service=flashpoint_service,
            )

            if await _scan_is_inactive_async(session, redis_conn, scan_uuid):
                logger.info(
                    "Flashpoint step skipped because scan is already terminal/finalizing",
                    extra={"scan_id": scan_id, "batch_number": batch_number},
                )
                return {"flashpoint_candidates_key": "", "candidate_count": 0}

            message_id_index = service._build_message_id_index(channel_context_map)

            candidates = []
            for msg in typed_messages:
                if not msg.content or len(msg.content.strip()) < 10:
                    continue
                context_messages = service._get_context_for_message(
                    msg, channel_context_map, message_id_index
                )
                candidate = await service._flashpoint_scan_candidate(
                    scan_uuid, msg, context_messages
                )
                if candidate:
                    candidates.append(candidate)
            if await _skip_step_persist_if_scan_terminal(
                session,
                redis_conn,
                scan_uuid,
                step_name="Flashpoint",
                scan_id=scan_id,
                batch_number=batch_number,
            ):
                return {"flashpoint_candidates_key": "", "candidate_count": 0}

            candidates_key = get_batch_redis_key(scan_id, batch_number, "flashpoint_candidates")
            candidates_data = [c.model_dump(mode="json") for c in candidates]
            await store_messages_in_redis(redis_conn, candidates_key, candidates_data)

            logger.info(
                "Flashpoint scan step completed",
                extra={
                    "scan_id": scan_id,
                    "batch_number": batch_number,
                    "candidate_count": len(candidates),
                },
            )

            return {
                "flashpoint_candidates_key": candidates_key,
                "candidate_count": len(candidates),
            }

    timeout = max(
        120.0, settings.FLASHPOINT_MAX_BATCH_MESSAGES * settings.FLASHPOINT_TIMEOUT_PER_MESSAGE
    )
    return run_sync(_flashpoint_scan(), timeout=timeout)


@DBOS.step()
def content_reviewer_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    similarity_candidates_key: str,
    flashpoint_candidates_key: str,
) -> dict[str, Any]:
    """Run ContentReviewerAgent + ModerationPolicyEvaluator on all scan candidates.

    Loads similarity and flashpoint candidates from Redis, groups them by message_id
    into evidence bundles, invokes ContentReviewerService.classify() once per unique
    message with all pre-computed evidence, applies ModerationPolicyEvaluator, and
    stores flagged results.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        similarity_candidates_key: Redis key with similarity candidates
        flashpoint_candidates_key: Redis key with flashpoint candidates

    Returns:
        dict with: flagged_count, errors, policy_decisions
    """
    from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService
    from src.bulk_content_scan.policy_evaluator import (
        ModerationPolicyConfig,
        ModerationPolicyEvaluator,
    )
    from src.bulk_content_scan.schemas import (
        BulkScanMessage,
        FlaggedMessage,
        ScanCandidate,
        bulk_scan_message_to_content_item,
    )
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService

    settings = get_settings()
    scan_uuid = UUID(scan_id)

    async def _content_reviewer() -> dict[str, Any]:  # noqa: PLR0912
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)

        all_candidates: list[ScanCandidate] = []
        errors = 0

        if similarity_candidates_key:
            try:
                sim_data = await load_messages_from_redis(redis_conn, similarity_candidates_key)
                all_candidates.extend(ScanCandidate.model_validate(c) for c in sim_data)
            except ValueError:
                logger.warning(
                    "Similarity candidates Redis key expired or missing",
                    extra={"scan_id": scan_id, "key": similarity_candidates_key},
                )
                errors += 1

        if flashpoint_candidates_key:
            try:
                fp_data = await load_messages_from_redis(redis_conn, flashpoint_candidates_key)
                all_candidates.extend(ScanCandidate.model_validate(c) for c in fp_data)
            except ValueError:
                logger.warning(
                    "Flashpoint candidates Redis key expired or missing",
                    extra={"scan_id": scan_id, "key": flashpoint_candidates_key},
                )
                errors += 1

        if not all_candidates:
            return {"flagged_count": 0, "errors": errors, "policy_decisions": []}

        async with get_session_maker()() as session:
            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            from src.bulk_content_scan.flashpoint_service import get_flashpoint_service

            flashpoint_service = get_flashpoint_service()
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
                flashpoint_service=flashpoint_service,
            )

            if await _scan_is_inactive_async(session, redis_conn, scan_uuid):
                logger.info(
                    "Content reviewer step skipped because scan is already terminal/finalizing",
                    extra={"scan_id": scan_id, "batch_number": batch_number},
                )
                return {"flagged_count": 0, "errors": errors, "policy_decisions": []}

            evidence_by_message: dict[str, list[ScanCandidate]] = {}
            for candidate in all_candidates:
                msg_id = candidate.message.message_id
                evidence_by_message.setdefault(msg_id, []).append(candidate)

            reviewer_service = ContentReviewerService()
            evaluator = ModerationPolicyEvaluator()
            policy_config = ModerationPolicyConfig()

            flagged_messages: list[FlaggedMessage] = []
            policy_decisions: list[dict[str, Any]] = []

            try:
                for msg_id, candidates in evidence_by_message.items():
                    pre_computed = [c.match_data for c in candidates]
                    content_item = bulk_scan_message_to_content_item(candidates[0].message)

                    channel_id = candidates[0].message.channel_id
                    flashpoint_ctx_data_key = (
                        f"{settings.ENVIRONMENT}:flashpoint_ctx"
                        f":{community_server_id}:{channel_id}:data"
                    )
                    try:
                        cached_channel_data = await redis_conn.hgetall(flashpoint_ctx_data_key)  # type: ignore[misc]
                        context_items_for_msg = [
                            bulk_scan_message_to_content_item(
                                BulkScanMessage.model_validate_json(raw_json)
                            )
                            for cached_msg_id_raw, raw_json in cached_channel_data.items()
                            if (
                                cached_msg_id_raw.decode("utf-8")
                                if isinstance(cached_msg_id_raw, bytes)
                                else cached_msg_id_raw
                            )
                            != msg_id
                        ]
                        if not context_items_for_msg:
                            logger.warning(
                                "No flashpoint channel context available in cache for message",
                                extra={
                                    "scan_id": scan_id,
                                    "msg_id": msg_id,
                                    "channel_id": channel_id,
                                    "community_server_id": community_server_id,
                                },
                            )
                    except Exception:
                        logger.warning(
                            "Failed to load flashpoint channel context from Redis cache",
                            extra={
                                "scan_id": scan_id,
                                "msg_id": msg_id,
                                "channel_id": channel_id,
                                "community_server_id": community_server_id,
                            },
                        )
                        context_items_for_msg = []
                    classification = await reviewer_service.classify(
                        content_item=content_item,
                        pre_computed_evidence=pre_computed,  # type: ignore[arg-type]
                        context_items=context_items_for_msg,
                        flashpoint_service=flashpoint_service,
                        model=settings.CONTENT_REVIEWER_MODEL,
                    )

                    if classification.error_type is not None:
                        from src.monitoring.metrics import (
                            content_reviewer_error_classifications_total,
                        )

                        logger.warning(
                            "ContentReviewerAgent hard failure; routing as pass (fail-open)",
                            extra={
                                "scan_id": scan_id,
                                "msg_id": msg_id,
                                "classification_error_type": classification.error_type,
                                "explanation": classification.explanation,
                            },
                        )
                        content_reviewer_error_classifications_total.add(
                            1, {"error_type": classification.error_type}
                        )

                    policy_decision = evaluator.evaluate(classification, policy_config)

                    if policy_decision.action_tier is not None:
                        from src.bulk_content_scan.action_bridge import (
                            create_moderation_action_from_policy,
                            emit_platform_action_event,
                        )
                        from src.moderation_actions.models import ActionTier

                        request_id = uuid_module.uuid5(
                            uuid_module.NAMESPACE_URL,
                            f"bulk-scan:{scan_id}:{msg_id}",
                        )
                        community_server_uuid = UUID(community_server_id)
                        (
                            moderation_action,
                            newly_created,
                        ) = await create_moderation_action_from_policy(
                            session=session,
                            policy_decision=policy_decision,
                            classification=classification,
                            content_item=content_item,
                            request_id=request_id,
                            community_server_id=community_server_uuid,
                            pre_computed_evidence=pre_computed,  # type: ignore[arg-type]
                        )

                        if (
                            moderation_action is not None
                            and newly_created
                            and policy_decision.action_tier == ActionTier.TIER_1_IMMEDIATE
                        ):
                            from src.events.publisher import create_worker_event_publisher

                            async with create_worker_event_publisher() as worker_publisher:
                                await emit_platform_action_event(
                                    publisher=worker_publisher,
                                    moderation_action=moderation_action,
                                    content_item=content_item,
                                )

                        first_candidate = candidates[0]
                        matches = [c.match_data for c in candidates]
                        matches.append(classification)
                        flagged_msg = FlaggedMessage(
                            message_id=first_candidate.message.message_id,
                            channel_id=first_candidate.message.channel_id,
                            content=first_candidate.message.content,
                            author_id=first_candidate.message.author_id,
                            timestamp=first_candidate.message.timestamp,
                            matches=matches,
                        )
                        flagged_messages.append(flagged_msg)

                    policy_decisions.append(
                        {
                            "message_id": msg_id,
                            "action_tier": getattr(policy_decision.action_tier, "value", None),
                            "action_type": getattr(policy_decision.action_type, "value", None),
                            "review_group": getattr(policy_decision.review_group, "value", None),
                            "reason": policy_decision.reason,
                        }
                    )

                if await _skip_step_persist_if_scan_terminal(
                    session,
                    redis_conn,
                    scan_uuid,
                    step_name="ContentReviewer",
                    scan_id=scan_id,
                    batch_number=batch_number,
                ):
                    return {"flagged_count": 0, "errors": errors, "policy_decisions": []}

                for msg in flagged_messages:
                    await service.append_flagged_result(scan_uuid, msg)

                return {
                    "flagged_count": len(flagged_messages),
                    "errors": errors,
                    "policy_decisions": policy_decisions,
                }

            except Exception as e:
                logger.warning(
                    "Error in content reviewer step",
                    extra={
                        "scan_id": scan_id,
                        "batch_number": batch_number,
                        "error": str(e),
                    },
                )
                if await _skip_step_persist_if_scan_terminal(
                    session,
                    redis_conn,
                    scan_uuid,
                    step_name="ContentReviewer",
                    scan_id=scan_id,
                    batch_number=batch_number,
                ):
                    return {"flagged_count": 0, "errors": errors, "policy_decisions": []}

                await service.record_error(
                    scan_id=scan_uuid,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    batch_number=batch_number,
                )
                return {
                    "flagged_count": 0,
                    "errors": errors + len(all_candidates),
                    "policy_decisions": [],
                }

    return run_sync(_content_reviewer())


@DBOS.step()
def relevance_filter_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    similarity_candidates_key: str,
    flashpoint_candidates_key: str,
) -> dict[str, Any]:
    """Run unified relevance filtering on all candidates.

    DEPRECATED: Use content_reviewer_step instead. This step is preserved for
    backward compatibility and will be removed in a follow-up task.

    Reads similarity and flashpoint candidates from Redis, runs the LLM
    relevance check, and appends flagged results to scan results.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        similarity_candidates_key: Redis key with similarity candidates
        flashpoint_candidates_key: Redis key with flashpoint candidates

    Returns:
        dict with: flagged_count, errors
    """
    from src.bulk_content_scan.flashpoint_service import get_flashpoint_service
    from src.bulk_content_scan.schemas import ScanCandidate
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.fact_checking.embedding_service import EmbeddingService

    settings = get_settings()
    scan_uuid = UUID(scan_id)

    async def _relevance_filter() -> dict[str, Any]:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)

        all_candidates: list[ScanCandidate] = []
        errors = 0

        if similarity_candidates_key:
            try:
                sim_data = await load_messages_from_redis(redis_conn, similarity_candidates_key)
                all_candidates.extend(ScanCandidate.model_validate(c) for c in sim_data)
            except ValueError:
                logger.warning(
                    "Similarity candidates Redis key expired or missing",
                    extra={"scan_id": scan_id, "key": similarity_candidates_key},
                )
                errors += 1

        if flashpoint_candidates_key:
            try:
                fp_data = await load_messages_from_redis(redis_conn, flashpoint_candidates_key)
                all_candidates.extend(ScanCandidate.model_validate(c) for c in fp_data)
            except ValueError:
                logger.warning(
                    "Flashpoint candidates Redis key expired or missing",
                    extra={"scan_id": scan_id, "key": flashpoint_candidates_key},
                )
                errors += 1

        if not all_candidates:
            return {"flagged_count": 0, "errors": errors}

        async with get_session_maker()() as session:
            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            flashpoint_service = get_flashpoint_service()
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
                flashpoint_service=flashpoint_service,
            )

            if await _scan_is_inactive_async(session, redis_conn, scan_uuid):
                logger.info(
                    "Relevance step skipped because scan is already terminal/finalizing",
                    extra={"scan_id": scan_id, "batch_number": batch_number},
                )
                return {"flagged_count": 0, "errors": errors}

            try:
                flagged = await service._filter_candidates_with_relevance(all_candidates, scan_uuid)
                if await _skip_step_persist_if_scan_terminal(
                    session,
                    redis_conn,
                    scan_uuid,
                    step_name="Relevance",
                    scan_id=scan_id,
                    batch_number=batch_number,
                ):
                    return {"flagged_count": 0, "errors": errors}

                for msg in flagged:
                    await service.append_flagged_result(scan_uuid, msg)

                return {"flagged_count": len(flagged), "errors": errors}
            except Exception as e:
                logger.warning(
                    "Error in relevance filter step",
                    extra={
                        "scan_id": scan_id,
                        "batch_number": batch_number,
                        "error": str(e),
                    },
                )
                if await _skip_step_persist_if_scan_terminal(
                    session,
                    redis_conn,
                    scan_uuid,
                    step_name="Relevance",
                    scan_id=scan_id,
                    batch_number=batch_number,
                ):
                    return {"flagged_count": 0, "errors": errors}

                await service.record_error(
                    scan_id=scan_uuid,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    batch_number=batch_number,
                )
                return {"flagged_count": 0, "errors": errors + len(all_candidates)}

    return run_sync(_relevance_filter())


def _determine_scan_status(
    messages_scanned: int,
    processed_count: int,
    error_count: int,
    total_errors: int,
    skipped_count: int = 0,
    all_transmitted_observed: bool = True,
    finalization_incomplete: bool = False,
) -> tuple[BulkScanStatus, str | None]:
    status = BulkScanStatus.COMPLETED
    failure_reason = None

    if (
        not all_transmitted_observed
        and messages_scanned == 0
        and processed_count == 0
        and error_count == 0
        and total_errors == 0
    ):
        status = BulkScanStatus.FAILED
        failure_reason = "zero-message scan never observed all_transmitted"
    elif messages_scanned > 0 and finalization_incomplete:
        status = BulkScanStatus.FAILED
        failure_reason = "finalization incomplete after all_transmitted handoff"
    elif messages_scanned > 0 and processed_count == 0 and total_errors > 0:
        status = BulkScanStatus.FAILED
        failure_reason = "100% of messages had errors"
    elif messages_scanned > 0 and processed_count == 0 and error_count > 0:
        status = BulkScanStatus.FAILED
        failure_reason = "all messages had batch errors"
    elif (
        messages_scanned > 0
        and processed_count == 0
        and skipped_count == messages_scanned
        and error_count == 0
        and total_errors == 0
    ):
        failure_reason = None
    elif messages_scanned > 0 and processed_count == 0 and error_count == 0 and total_errors == 0:
        status = BulkScanStatus.FAILED
        failure_reason = "orchestrator timed out with zero messages processed"

    return status, failure_reason


@DBOS.step()
def finalize_scan_step(
    scan_id: str,
    community_server_id: str,
    messages_scanned: int,
    processed_count: int,
    skipped_count: int,
    error_count: int,
    flagged_count: int,
    all_transmitted_observed: bool = True,
    finalization_incomplete: bool = False,
) -> dict[str, Any]:
    """Finalize the content scan: update DB record and publish NATS events.

    Uses SELECT...FOR UPDATE for the DB update to prevent race conditions.
    Publishes bulk-scan terminal events after persisting the final DB status.
    Completed scans publish results + processing finished. Failed scans publish
    results + failed + processing finished.

    Args:
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        messages_scanned: Total messages scanned
        processed_count: Successfully processed messages
        skipped_count: Skipped messages (already had note requests)
        error_count: Messages that failed processing
        flagged_count: Messages that were flagged

    Returns:
        dict with scan finalization results
    """
    from src.bulk_content_scan.nats_handler import BulkScanResultsPublisher
    from src.bulk_content_scan.schemas import BulkScanStatus
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.dbos_workflows.content_monitoring_workflows import _get_llm_service
    from src.events.publisher import create_worker_event_publisher
    from src.events.schemas import (
        BulkScanFailedEvent,
        BulkScanProcessingFinishedEvent,
        ScanErrorInfo,
        ScanErrorSummary,
    )
    from src.fact_checking.embedding_service import EmbeddingService
    from src.monitoring.metrics import bulk_scan_finalization_dispatch_total

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)

    async def _finalize() -> dict[str, Any]:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)

        async with get_session_maker()() as session:
            llm_service = _get_llm_service()
            embedding_service = EmbeddingService(llm_service)
            service = BulkContentScanService(
                session=session,
                embedding_service=embedding_service,
                redis_client=redis_conn,
                llm_service=llm_service,
            )

            flagged = await service.get_flagged_results(scan_uuid)
            error_summary_data = await service.get_error_summary(scan_uuid)
            redis_skipped_count = await service.get_skipped_count(scan_uuid)
            effective_skipped_count = (
                skipped_count if redis_skipped_count != skipped_count else redis_skipped_count
            )

            if redis_skipped_count != skipped_count:
                logger.warning(
                    "Skipped count drift detected during finalization; using workflow count",
                    extra={
                        "scan_id": scan_id,
                        "workflow_skipped_count": skipped_count,
                        "redis_skipped_count": redis_skipped_count,
                    },
                )

            total_errors = error_summary_data.get("total_errors", 0)
            error_types = error_summary_data.get("error_types", {})
            sample_errors = error_summary_data.get("sample_errors", [])

            error_summary = None
            if total_errors > 0:
                error_summary = ScanErrorSummary(
                    total_errors=total_errors,
                    error_types=error_types,
                    sample_errors=[
                        ScanErrorInfo(
                            error_type=err.get("error_type", "Unknown"),
                            message_id=err.get("message_id"),
                            batch_number=err.get("batch_number"),
                            error_message=err.get("error_message", ""),
                        )
                        for err in sample_errors
                    ],
                )

            status, failure_reason = _determine_scan_status(
                messages_scanned=messages_scanned,
                processed_count=processed_count,
                skipped_count=effective_skipped_count,
                error_count=error_count,
                total_errors=total_errors,
                all_transmitted_observed=all_transmitted_observed,
                finalization_incomplete=finalization_incomplete,
            )
            if status == BulkScanStatus.FAILED:
                logger.warning(
                    "Scan marked as failed: %s",
                    failure_reason,
                    extra={
                        "scan_id": scan_id,
                        "messages_scanned": messages_scanned,
                        "processed_count": processed_count,
                        "total_errors": total_errors,
                        "failure_reason": failure_reason,
                    },
                )

            await service.complete_scan(
                scan_id=scan_uuid,
                messages_scanned=messages_scanned,
                messages_flagged=len(flagged),
                status=status,
            )

            async with create_worker_event_publisher() as worker_publisher:
                publisher = BulkScanResultsPublisher(worker_publisher.nats)
                await publisher.publish(
                    scan_id=scan_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                    messages_skipped=effective_skipped_count,
                    flagged_messages=flagged,
                    error_summary=error_summary,
                )

                if status == BulkScanStatus.FAILED:
                    failed_event = BulkScanFailedEvent(
                        event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
                        scan_id=scan_uuid,
                        community_server_id=community_uuid,
                        error_message=failure_reason or "bulk scan failed without a reason",
                    )
                    await worker_publisher.publish_event(failed_event)

                processing_finished_event = BulkScanProcessingFinishedEvent(
                    event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
                    scan_id=scan_uuid,
                    community_server_id=community_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                    messages_skipped=effective_skipped_count,
                )
                await worker_publisher.publish_event(processing_finished_event)

            logger.info(
                "Scan finalized via DBOS workflow",
                extra={
                    "scan_id": scan_id,
                    "messages_scanned": messages_scanned,
                    "processed_count": processed_count,
                    "error_count": error_count,
                    "messages_flagged": len(flagged),
                    "messages_skipped": effective_skipped_count,
                    "status": status.value,
                    "total_errors": total_errors,
                },
            )

            return {
                "status": status.value,
                "messages_scanned": messages_scanned,
                "messages_flagged": len(flagged),
                "messages_skipped": effective_skipped_count,
                "total_errors": total_errors,
            }

    try:
        result = run_sync(_finalize())
        bulk_scan_finalization_dispatch_total.add(1, {"outcome": "success"})
        return result
    except Exception:
        bulk_scan_finalization_dispatch_total.add(1, {"outcome": "error"})
        raise


async def dispatch_content_scan_workflow(
    scan_id: UUID,
    community_server_id: UUID,
    scan_types: list[str],
) -> str | None:
    """Dispatch a DBOS content scan orchestration workflow.

    Uses the scan_id as the workflow ID for idempotency.

    Args:
        scan_id: UUID of the scan (from BulkContentScanLog)
        community_server_id: UUID of the community server
        scan_types: List of scan type strings

    Returns:
        The DBOS workflow_id if successfully started, None on failure
    """
    try:
        scan_types_json = orjson.dumps(scan_types).decode()

        def _enqueue():
            with SetWorkflowID(str(scan_id)), SetEnqueueOptions(deduplication_id=str(scan_id)):
                return content_scan_queue.enqueue(
                    content_scan_orchestration_workflow,
                    str(scan_id),
                    str(community_server_id),
                    scan_types_json,
                )

        handle = await safe_enqueue(_enqueue)

        logger.info(
            "Content scan DBOS workflow dispatched",
            extra={
                "scan_id": str(scan_id),
                "workflow_id": handle.workflow_id,
                "community_server_id": str(community_server_id),
            },
        )

        return handle.workflow_id

    except Exception as e:
        logger.error(
            "Failed to dispatch content scan DBOS workflow",
            extra={
                "scan_id": str(scan_id),
                "error": str(e),
            },
            exc_info=True,
        )
        return None


async def enqueue_content_scan_batch(
    orchestrator_workflow_id: str,
    scan_id: UUID,
    community_server_id: UUID,
    batch_number: int,
    scan_types: list[str],
    messages_redis_key: str,
) -> str | None:
    """Enqueue a content scan batch for processing via DBOS queue.

    Messages must already be stored in Redis under messages_redis_key.
    The workflow reads messages from Redis instead of receiving them via
    the DBOS checkpoint (keeping large payloads out of the DBOS system
    tables).

    Args:
        orchestrator_workflow_id: Workflow ID of the orchestrator to signal on completion
        scan_id: UUID of the scan
        community_server_id: UUID of the community server
        batch_number: Batch number
        scan_types: List of scan type strings
        messages_redis_key: Redis key where messages are stored

    Returns:
        The DBOS workflow_id if successfully enqueued, None on failure
    """

    try:
        scan_types_json = orjson.dumps(scan_types).decode()

        def _enqueue():
            return content_scan_queue.enqueue(
                process_content_scan_batch,
                orchestrator_workflow_id,
                str(scan_id),
                str(community_server_id),
                batch_number,
                messages_redis_key,
                scan_types_json,
            )

        handle = await safe_enqueue(_enqueue)

        logger.info(
            "Content scan batch enqueued via DBOS",
            extra={
                "scan_id": str(scan_id),
                "batch_number": batch_number,
                "workflow_id": handle.workflow_id,
                "messages_redis_key": messages_redis_key,
            },
        )

        return handle.workflow_id

    except Exception as e:
        logger.error(
            "Failed to enqueue content scan batch via DBOS",
            extra={
                "scan_id": str(scan_id),
                "batch_number": batch_number,
                "error": str(e),
            },
            exc_info=True,
        )
        return None


async def send_all_transmitted_signal(
    orchestrator_workflow_id: str,
    messages_scanned: int,
) -> bool:
    """Send the all_transmitted signal to the orchestrator workflow.

    Args:
        orchestrator_workflow_id: Workflow ID of the orchestrator
        messages_scanned: Total messages that were transmitted

    Returns:
        True if signal sent successfully, False on failure
    """
    try:
        await asyncio.to_thread(
            DBOS.send,
            orchestrator_workflow_id,
            {"messages_scanned": messages_scanned},
            "all_transmitted",
        )

        logger.info(
            "Sent all_transmitted signal to orchestrator",
            extra={
                "orchestrator_workflow_id": orchestrator_workflow_id,
                "messages_scanned": messages_scanned,
            },
        )

        return True

    except Exception as e:
        logger.error(
            "Failed to send all_transmitted signal",
            extra={
                "orchestrator_workflow_id": orchestrator_workflow_id,
                "error": str(e),
            },
            exc_info=True,
        )
        return False


CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME: str = content_scan_orchestration_workflow.__qualname__
PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME: str = process_content_scan_batch.__qualname__
