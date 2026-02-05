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
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid as uuid_module
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dbos import DBOS, Queue

from src.monitoring import get_logger
from src.utils.async_compat import run_sync

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

content_scan_queue = Queue(
    name="content_scan",
    worker_concurrency=2,
    concurrency=4,
)

BATCH_RECV_TIMEOUT_SECONDS = 600
POST_ALL_TRANSMITTED_TIMEOUT_SECONDS = 60
SCAN_RECV_TIMEOUT_SECONDS = 0
ORCHESTRATOR_MAX_WALL_CLOCK_SECONDS = 1800


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
            POST_ALL_TRANSMITTED_TIMEOUT_SECONDS if all_transmitted else BATCH_RECV_TIMEOUT_SECONDS
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

        tx_recheck = DBOS.recv("all_transmitted", timeout_seconds=SCAN_RECV_TIMEOUT_SECONDS)
        if tx_recheck is not None:
            messages_scanned = tx_recheck.get("messages_scanned", messages_scanned)

        logger.warning(
            "Orchestrator detected count mismatch after all_transmitted - proceeding to finalization",
            extra={
                "scan_id": scan_id,
                "messages_scanned": messages_scanned,
                "processed_count": processed_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "actual_total": processed_count + skipped_count + error_count,
                "missing_count": messages_scanned - (processed_count + skipped_count + error_count),
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
    messages_json: str,
    scan_types_json: str,
) -> dict[str, Any]:
    """DBOS queued workflow for processing a single content scan batch.

    This workflow processes messages through the BulkContentScanService and
    sends a batch_complete signal back to the orchestrator when done.

    Args:
        orchestrator_workflow_id: Workflow ID of the orchestrator to signal
        scan_id: UUID string of the scan
        community_server_id: UUID string of the community server
        batch_number: Batch number being processed
        messages_json: JSON-encoded list of message dicts
        scan_types_json: JSON-encoded list of scan type strings

    Returns:
        dict with batch processing results
    """
    logger.info(
        "Starting content scan batch processing",
        extra={
            "scan_id": scan_id,
            "batch_number": batch_number,
            "orchestrator_workflow_id": orchestrator_workflow_id,
        },
    )

    result = process_batch_messages_step(
        scan_id=scan_id,
        community_server_id=community_server_id,
        batch_number=batch_number,
        messages_json=messages_json,
        scan_types_json=scan_types_json,
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

    async def _process() -> dict[str, Any]:
        from sqlalchemy import select

        redis_conn = await get_shared_redis_client(settings.REDIS_URL)

        async with get_session_maker()() as session:
            result = await session.execute(
                select(CommunityServer.platform_community_server_id).where(
                    CommunityServer.id == community_uuid
                )
            )
            platform_id = result.scalar_one_or_none()

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

            typed_messages = [BulkScanMessage.model_validate(msg) for msg in messages]

            try:
                flagged = await service.process_messages(
                    scan_id=scan_uuid,
                    messages=typed_messages,
                    community_server_platform_id=platform_id,
                    scan_types=scan_types,
                )
                processed = len(typed_messages)
                errors = 0
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

        handle = await asyncio.to_thread(
            client.start_workflow,  # pyright: ignore[reportAttributeAccessIssue]
            content_scan_orchestration_workflow,
            str(scan_id),
            str(community_server_id),
            scan_types_json,
            idempotency_key=str(scan_id),
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
    messages: list[dict[str, Any]],
    scan_types: list[str],
) -> str | None:
    """Enqueue a content scan batch for processing via DBOS queue.

    Args:
        orchestrator_workflow_id: Workflow ID of the orchestrator to signal on completion
        scan_id: UUID of the scan
        community_server_id: UUID of the community server
        batch_number: Batch number
        messages: List of message dicts
        scan_types: List of scan type strings

    Returns:
        The DBOS workflow_id if successfully enqueued, None on failure
    """
    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    try:
        client = get_dbos_client()
        messages_json = json.dumps(messages)
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
            messages_json,
            scan_types_json,
        )

        logger.info(
            "Content scan batch enqueued via DBOS",
            extra={
                "scan_id": str(scan_id),
                "batch_number": batch_number,
                "workflow_id": handle.workflow_id,
                "message_count": len(messages),
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


CONTENT_SCAN_ORCHESTRATION_WORKFLOW_NAME: str = (
    f"{__name__}.{content_scan_orchestration_workflow.__name__}"
)
PROCESS_CONTENT_SCAN_BATCH_WORKFLOW_NAME: str = f"{__name__}.{process_content_scan_batch.__name__}"
