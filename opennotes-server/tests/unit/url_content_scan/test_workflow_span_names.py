from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_run_safety_recommendation_span_name():
    from src.dbos_workflows.url_scan_workflow import _run_safety_recommendation

    spans_started: list[str] = []

    class _FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class _FakeTracer:
        def start_as_current_span(self, name: str, **kwargs):
            spans_started.append(name)
            return _FakeSpan()

    fake_slot_results: dict = {
        "slots": {},
        "done_count": 0,
        "failed_count": 0,
    }

    with (
        patch("src.dbos_workflows.url_scan_workflow._tracer", _FakeTracer()),
        patch("src.dbos_workflows.url_scan_workflow.run_sync") as mock_run_sync,
        patch("src.dbos_workflows.url_scan_workflow.run_safety_recommendation") as mock_rec,
        patch("src.dbos_workflows.url_scan_workflow.import_module") as mock_import,
    ):
        mock_inputs_cls = MagicMock()
        mock_import.return_value = MagicMock(SafetyRecommendationInputs=mock_inputs_cls)
        mock_recommendation = MagicMock()
        mock_recommendation.model_dump.return_value = {}
        mock_run_sync.return_value = mock_recommendation
        mock_rec.return_value = None

        _run_safety_recommendation("job-123", fake_slot_results)

    assert any("url_scan.with_utterances" in name for name in spans_started), (
        f"Expected url_scan.with_utterances span, got: {spans_started}"
    )
    assert not any("post_gemini" in name for name in spans_started), (
        f"Should not have post_gemini span, got: {spans_started}"
    )


def test_maybe_run_headline_summary_span_name():
    from src.dbos_workflows.url_scan_workflow import _maybe_run_headline_summary

    spans_started: list[str] = []

    class _FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class _FakeTracer:
        def start_as_current_span(self, name: str, **kwargs):
            spans_started.append(name)
            return _FakeSpan()

    extracted_payload = {
        "page_title": "Test Page",
        "page_kind": "other",
        "utterances": [],
        "scraped_at": "2024-01-01T00:00:00Z",
    }
    slot_results = {
        "slots": {},
        "done_count": 0,
        "failed_count": 0,
    }

    with (
        patch("src.dbos_workflows.url_scan_workflow._tracer", _FakeTracer()),
        patch("src.dbos_workflows.url_scan_workflow._run_headline_summary_inner") as mock_inner,
    ):
        mock_inner.return_value = {"headline": None}
        _maybe_run_headline_summary(
            job_id="job-456",
            extracted_payload=extracted_payload,
            slot_results=slot_results,
            safety_result=None,
        )

    assert any("url_scan.with_utterances" in name for name in spans_started), (
        f"Expected url_scan.with_utterances span, got: {spans_started}"
    )
    assert not any("post_gemini" in name for name in spans_started), (
        f"Should not have post_gemini span, got: {spans_started}"
    )
