from __future__ import annotations

from dbos import DBOS

from src.dbos_workflows.url_scan_workflow import (
    UrlScanWorkflowInputs,
    rotate_url_scan_section_attempt_step,
    url_scan_section_workflow,
)


@DBOS.workflow()
def url_scan_section_retry_workflow(
    job_id: str,
    section_slug: str,
    section_inputs: UrlScanWorkflowInputs,
    *,
    attempt_id: str | None = None,
    parent_holds_token: bool = False,
) -> dict[str, object]:
    new_attempt_id = rotate_url_scan_section_attempt_step(job_id, section_slug, attempt_id)
    return url_scan_section_workflow(
        job_id=job_id,
        section_slug=section_slug,
        attempt_id=new_attempt_id,
        section_inputs=section_inputs,
        parent_holds_token=parent_holds_token,
    )
