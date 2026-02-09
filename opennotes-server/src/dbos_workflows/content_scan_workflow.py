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
import json
import time
import uuid as uuid_module
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, EnqueueOptions, Queue

from src.monitoring import get_logger
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)

REDIS_BATCH_TTL_SECONDS = 86400
REDIS_REPLAY_TTL_SECONDS = 7 * 24 * 3600

content_scan_queue = Queue(
    name="content_scan",
    worker_concurrency=2,
    concurrency=4,
)

BATCH_RECV_TIMEOUT_SECONDS = 600
POST_ALL_TRANSMITTED_TIMEOUT_SECONDS = 60
SCAN_RECV_TIMEOUT_SECONDS = 30
ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS = 1800


def get_batch_redis_key(scan_id: str, batch_number: int, suffix: str) -> str:
    from src.config import get_settings

    env = get_settings().ENVIRONMENT
    return f"{env}:bulk_scan:{suffix}:{scan_id}:{batch_number}"


async def store_messages_in_redis(
    redis_client: Redis,
    key: str,
    messages: list[dict[str, Any]],
    ttl: int = REDIS_BATCH_TTL_SECONDS,
) -> str:
    await redis_client.setex(key, ttl, json.dumps(messages).encode())
    return key


async def load_messages_from_redis(
    redis_client: Redis,
    key: str,
) -> list[dict[str, Any]]:
    data = await redis_client.get(key)
    if data is None:
        raise ValueError(f"Redis key {key} not found or expired")
    await redis_client.expire(key, REDIS_REPLAY_TTL_SECONDS)
    raw = data.decode() if isinstance(data, bytes) else data
    return json.loads(raw)


@DBOS.step()
def _checkpoint_wall_clock_step() -> float:
    """Return time.time() as a DBOS-checkpointed value.

    Using time.time() (wall-clock) instead of time.monotonic()
    ensures the recorded start time is meaningful across process restarts
    during DBOS replay.
    """
    return time.time()


@DBOS.workflow()
def content_scan_orchestration_workflow(
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
    messages_scanned = 0
    batches_completed = 0
    wall_clock_start = _checkpoint_wall_clock_step()

    tx_signal = DBOS.recv("all_transmitted", timeout_seconds=SCAN_RECV_TIMEOUT_SECONDS)
    if tx_signal is not None:
        all_transmitted = True
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

            if not all_transmitted:
                tx_signal = DBOS.recv("all_transmitted", timeout_seconds=0)
                if tx_signal is not None:
                    all_transmitted = True
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

            logger.warning(
                "Orchestrator detected count mismatch after all_transmitted - proceeding to finalization",
                extra={
                    "scan_id": scan_id,
                    "messages_scanned": messages_scanned,
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "error_count": error_count,
                    "actual_total": processed_count + skipped_count + error_count,
                    "missing_count": messages_scanned
                    - (processed_count + skipped_count + error_count),
                },
            )
            break

    result = finalize_scan_step(
        scan_id=scan_id,
        community_server_id=community_server_id,
        messages_scanned=messages_scanned,
        processed_count=processed_count,
        skipped_count=skipped_count,
        error_count=error_count,
        flagged_count=flagged_count,
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

    scan_types = json.loads(scan_types_json)

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

        if message_count > 0:
            filtered_messages_key = preprocess_result["filtered_messages_key"]
            context_maps_key = preprocess_result.get("context_maps_key", "")

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
                filter_result = relevance_filter_step(
                    scan_id=scan_id,
                    community_server_id=community_server_id,
                    batch_number=batch_number,
                    similarity_candidates_key=similarity_result.get(
                        "similarity_candidates_key", ""
                    ),
                    flashpoint_candidates_key=flashpoint_result.get(
                        "flashpoint_candidates_key", ""
                    ),
                )
                flagged_count = filter_result.get("flagged_count", 0)
                errors = filter_result.get("errors", 0) + len(step_errors)
            except Exception as e:
                logger.error("relevance_filter_step failed", exc_info=True)
                step_errors.append(f"relevance: {e}")
                errors = len(step_errors)
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
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer
    from src.tasks.content_monitoring_tasks import _get_llm_service

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)
    messages = json.loads(messages_json)
    scan_types = [ScanType(st) for st in json.loads(scan_types_json)]

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
    from src.bulk_content_scan.schemas import BulkScanMessage
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer
    from src.tasks.content_monitoring_tasks import _get_llm_service

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)
    scan_types = [ScanType(st) for st in json.loads(scan_types_json)]

    async def _preprocess() -> dict[str, Any]:
        from sqlalchemy import select

        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, messages_redis_key)
        typed_messages = [BulkScanMessage.model_validate(msg) for msg in raw_messages]
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

            platform_message_ids = [msg.message_id for msg in typed_messages]
            existing_ids = await service.get_existing_request_message_ids(platform_message_ids)
            skipped_count = 0

            if existing_ids:
                typed_messages = [
                    msg for msg in typed_messages if msg.message_id not in existing_ids
                ]
                skipped_count = original_count - len(typed_messages)
                await service.increment_skipped_count(scan_uuid, skipped_count)
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
                await service._populate_cross_batch_cache(typed_messages, platform_id)
                channel_context_map = {
                    ch: [m.model_dump(mode="json") for m in msgs] for ch, msgs in raw_map.items()
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
    from src.bulk_content_scan.schemas import BulkScanMessage
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.fact_checking.embedding_service import EmbeddingService
    from src.llm_config.models import CommunityServer
    from src.tasks.content_monitoring_tasks import _get_llm_service

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)

    async def _similarity_scan() -> dict[str, Any]:
        from sqlalchemy import select

        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, filtered_messages_key)
        typed_messages = [BulkScanMessage.model_validate(msg) for msg in raw_messages]

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

            candidates = []
            for msg in typed_messages:
                if not msg.content or len(msg.content.strip()) < 10:
                    continue
                candidate = await service._similarity_scan_candidate(scan_uuid, msg, platform_id)
                if candidate:
                    candidates.append(candidate)

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
    from src.bulk_content_scan.schemas import BulkScanMessage
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import get_shared_redis_client
    from src.config import get_settings
    from src.database import get_session_maker
    from src.fact_checking.embedding_service import EmbeddingService
    from src.tasks.content_monitoring_tasks import _get_llm_service

    settings = get_settings()
    scan_uuid = UUID(scan_id)

    async def _flashpoint_scan() -> dict[str, Any]:
        redis_conn = await get_shared_redis_client(settings.REDIS_URL)
        raw_messages = await load_messages_from_redis(redis_conn, filtered_messages_key)
        typed_messages = [BulkScanMessage.model_validate(msg) for msg in raw_messages]

        context_data = await load_messages_from_redis(redis_conn, context_maps_key)
        channel_context_raw: dict[str, list[dict[str, Any]]] = (
            context_data[0] if context_data else {}
        )
        channel_context_map: dict[str, list[BulkScanMessage]] = {}
        for ch_id, msg_dicts in channel_context_raw.items():
            channel_context_map[ch_id] = [BulkScanMessage.model_validate(m) for m in msg_dicts]

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

    return run_sync(_flashpoint_scan())


@DBOS.step()
def relevance_filter_step(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    similarity_candidates_key: str,
    flashpoint_candidates_key: str,
) -> dict[str, Any]:
    """Run unified relevance filtering on all candidates.

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
    from src.fact_checking.embedding_service import EmbeddingService
    from src.tasks.content_monitoring_tasks import _get_llm_service

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

            try:
                flagged = await service._filter_candidates_with_relevance(all_candidates, scan_uuid)

                for msg in flagged:
                    await service.append_flagged_result(scan_uuid, msg)

                return {"flagged_count": len(flagged), "errors": 0}
            except Exception as e:
                logger.warning(
                    "Error in relevance filter step",
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
                    batch_number=batch_number,
                )
                return {"flagged_count": 0, "errors": len(all_candidates)}

    return run_sync(_relevance_filter())


@DBOS.step()
def finalize_scan_step(
    scan_id: str,
    community_server_id: str,
    messages_scanned: int,
    processed_count: int,
    skipped_count: int,
    error_count: int,
    flagged_count: int,
) -> dict[str, Any]:
    """Finalize the content scan: update DB record and publish NATS events.

    Uses SELECT...FOR UPDATE for the DB update to prevent race conditions.
    Publishes BulkScanResultsEvent and BulkScanProcessingFinishedEvent.

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
    from src.events.publisher import create_worker_event_publisher
    from src.events.schemas import (
        BulkScanProcessingFinishedEvent,
        ScanErrorInfo,
        ScanErrorSummary,
    )
    from src.fact_checking.embedding_service import EmbeddingService
    from src.monitoring.metrics import bulk_scan_finalization_dispatch_total
    from src.tasks.content_monitoring_tasks import _get_llm_service

    settings = get_settings()
    scan_uuid = UUID(scan_id)
    community_uuid = UUID(community_server_id)
    instance_id = settings.INSTANCE_ID

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
            actual_skipped = await service.get_skipped_count(scan_uuid)

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

            status = BulkScanStatus.COMPLETED
            if messages_scanned > 0 and processed_count == 0 and total_errors > 0:
                status = BulkScanStatus.FAILED
                logger.warning(
                    "Scan marked as failed - 100% of messages had errors",
                    extra={
                        "scan_id": scan_id,
                        "messages_scanned": messages_scanned,
                        "total_errors": total_errors,
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
                    messages_skipped=actual_skipped,
                    flagged_messages=flagged,
                    error_summary=error_summary,
                )

                processing_finished_event = BulkScanProcessingFinishedEvent(
                    event_id=f"evt_{uuid_module.uuid4().hex[:12]}",
                    scan_id=scan_uuid,
                    community_server_id=community_uuid,
                    messages_scanned=messages_scanned,
                    messages_flagged=len(flagged),
                    messages_skipped=actual_skipped,
                )
                await worker_publisher.publish_event(processing_finished_event)

            logger.info(
                "Scan finalized via DBOS workflow",
                extra={
                    "scan_id": scan_id,
                    "messages_scanned": messages_scanned,
                    "messages_flagged": len(flagged),
                    "messages_skipped": actual_skipped,
                    "status": status.value,
                    "total_errors": total_errors,
                },
            )

            return {
                "status": status.value,
                "messages_scanned": messages_scanned,
                "messages_flagged": len(flagged),
                "messages_skipped": actual_skipped,
                "total_errors": total_errors,
            }

    try:
        result = run_sync(_finalize())
        bulk_scan_finalization_dispatch_total.labels(
            outcome="success", instance_id=instance_id
        ).inc()
        return result
    except Exception:
        bulk_scan_finalization_dispatch_total.labels(outcome="error", instance_id=instance_id).inc()
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
    from src.dbos_workflows.config import get_dbos_client

    try:
        client = get_dbos_client()
        scan_types_json = json.dumps(scan_types)

        options: EnqueueOptions = {
            "queue_name": "content_scan",
            "workflow_name": CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME,
            "workflow_id": str(scan_id),
            "deduplication_id": str(scan_id),
        }
        handle = await asyncio.to_thread(
            client.enqueue,
            options,
            str(scan_id),
            str(community_server_id),
            scan_types_json,
        )

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

    from src.dbos_workflows.config import get_dbos_client

    try:
        client = get_dbos_client()
        scan_types_json = json.dumps(scan_types)

        options: EnqueueOptions = {
            "queue_name": "content_scan",
            "workflow_name": PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME,
        }

        handle = await asyncio.to_thread(
            client.enqueue,
            options,
            orchestrator_workflow_id,
            str(scan_id),
            str(community_server_id),
            batch_number,
            messages_redis_key,
            scan_types_json,
        )

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
    from src.dbos_workflows.config import get_dbos_client

    try:
        client = get_dbos_client()

        await asyncio.to_thread(
            client.send,
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
