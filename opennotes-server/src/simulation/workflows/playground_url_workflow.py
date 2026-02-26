from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from dbos import DBOS, Queue

from src.monitoring import get_logger
from src.utils.async_compat import run_sync

logger = get_logger(__name__)

playground_url_queue = Queue(
    name="playground_url_extraction",
    concurrency=5,
)

URL_STEP_MAX_ATTEMPTS = 3
URL_STEP_INTERVAL_SECONDS = 5.0
URL_STEP_BACKOFF_RATE = 2.0


@DBOS.step(
    retries_allowed=True,
    max_attempts=URL_STEP_MAX_ATTEMPTS,
    interval_seconds=URL_STEP_INTERVAL_SECONDS,
    backoff_rate=URL_STEP_BACKOFF_RATE,
)
def extract_and_create_request_step(
    url: str,
    community_server_id: str,
    requested_by: str,
) -> dict[str, Any]:
    from src.database import get_session_maker
    from src.notes.message_archive_service import MessageArchiveService
    from src.notes.models import Request
    from src.shared.content_extraction import ContentExtractionError, extract_content_from_url
    from src.simulation.playground_jsonapi_router import _validate_url_security

    request_id = f"playground-{uuid4().hex}"
    cs_uuid = UUID(community_server_id)

    try:
        _validate_url_security(url)
    except ValueError as exc:
        logger.warning(
            "URL failed SSRF validation in workflow step",
            extra={"url": url, "error": str(exc)},
        )
        return {
            "request_id": request_id,
            "url": url,
            "status": "FAILED",
            "error": "URL validation failed",
        }

    async def _process() -> dict[str, Any]:
        try:
            extracted = await asyncio.wait_for(
                extract_content_from_url(url),
                timeout=120,
            )
        except (ContentExtractionError, TimeoutError) as e:
            logger.warning(
                "Content extraction failed in workflow step",
                extra={"url": url, "error": str(e)},
            )
            error_msg = (
                str(e) if isinstance(e, ContentExtractionError) else "Content extraction timed out"
            )
            return {
                "request_id": request_id,
                "url": url,
                "status": "FAILED",
                "error": error_msg,
            }

        async with get_session_maker()() as session:
            message_archive = await MessageArchiveService.create_from_text(
                db=session,
                content=extracted.text,
            )
            message_archive.message_metadata = {
                "source_url": url,
                "domain": extracted.domain,
                "title": extracted.title,
                "extracted_at": extracted.extracted_at.isoformat(),
            }

            note_request = Request(
                request_id=request_id,
                requested_by=requested_by,
                community_server_id=cs_uuid,
                message_archive_id=message_archive.id,
            )
            session.add(note_request)
            await session.commit()

            return {
                "request_id": request_id,
                "url": url,
                "status": "PENDING",
                "content_preview": extracted.text[:500] if extracted.text else None,
            }

    return run_sync(_process())


@DBOS.step()
def set_workflow_result_step(
    results: list[dict[str, Any]],
    url_count: int,
) -> dict[str, Any]:
    succeeded = sum(1 for r in results if r["status"] == "PENDING")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    return {
        "url_count": url_count,
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


@DBOS.workflow()
def run_playground_url_extraction(
    urls_json: str,
    community_server_id: str,
    requested_by: str,
) -> dict[str, Any]:
    import json

    urls: list[str] = json.loads(urls_json)
    workflow_id = DBOS.workflow_id

    logger.info(
        "Starting playground URL extraction workflow",
        extra={
            "workflow_id": workflow_id,
            "url_count": len(urls),
            "community_server_id": community_server_id,
        },
    )

    results: list[dict[str, Any]] = []
    for url in urls:
        result = extract_and_create_request_step(url, community_server_id, requested_by)
        results.append(result)

    summary = set_workflow_result_step(results, len(urls))

    logger.info(
        "Playground URL extraction workflow completed",
        extra={
            "workflow_id": workflow_id,
            "succeeded": summary["succeeded"],
            "failed": summary["failed"],
        },
    )

    return summary


RUN_PLAYGROUND_URL_EXTRACTION_NAME: str = run_playground_url_extraction.__qualname__


async def dispatch_playground_url_extraction(
    urls: list[str],
    community_server_id: UUID,
    requested_by: str,
) -> str:
    import json

    from dbos import EnqueueOptions

    from src.dbos_workflows.config import get_dbos_client

    client = get_dbos_client()
    wf_id = f"playground-urls-{uuid4().hex}"
    options: EnqueueOptions = {
        "queue_name": "playground_url_extraction",
        "workflow_name": RUN_PLAYGROUND_URL_EXTRACTION_NAME,
        "workflow_id": wf_id,
        "deduplication_id": wf_id,
    }

    urls_json = json.dumps(urls)
    handle = await asyncio.to_thread(
        client.enqueue,
        options,
        urls_json,
        str(community_server_id),
        requested_by,
    )

    logger.info(
        "Playground URL extraction workflow dispatched",
        extra={
            "workflow_id": handle.workflow_id,
            "url_count": len(urls),
            "community_server_id": str(community_server_id),
        },
    )

    return handle.workflow_id
