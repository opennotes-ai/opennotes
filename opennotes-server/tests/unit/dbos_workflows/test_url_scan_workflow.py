from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.url_scan_workflow import (
    UrlScanWorkflowInputs,
    _build_sidebar_payload,
    _execute_url_scan_section,
    _hydrate_section_inputs,
    _terminal_batch_status_for_results,
)
from src.url_content_scan.claims_schemas import ClaimsReport
from src.url_content_scan.opinions_schemas import SentimentStatsReport
from src.url_content_scan.safety_schemas import SafetyRecommendation
from src.url_content_scan.schemas import PageKind, SectionSlug
from src.url_content_scan.tone_schemas import SCDReport
from src.url_content_scan.utterances.schema import Utterance
from src.utils.async_compat import run_sync


def _utterance() -> Utterance:
    return Utterance(
        utterance_id="utt-1",
        kind="comment",
        text="hello world",
        author="alice",
    )


def _sentiment_stats() -> SentimentStatsReport:
    return SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=100.0,
        mean_valence=0.0,
    )


def _claims_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


def _scd_report() -> SCDReport:
    return SCDReport(
        narrative="calm conversation",
        speaker_arcs=[],
        summary="summary",
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=False,
    )


def _safety_recommendation() -> SafetyRecommendation:
    return SafetyRecommendation(
        level="safe",
        rationale="all clear",
        top_signals=[],
        unavailable_inputs=[],
    )


class TestSectionRunnerMap:
    def test_covers_all_section_slugs(self) -> None:
        from src.dbos_workflows.url_scan_workflow import _SECTION_RUNNERS

        assert set(_SECTION_RUNNERS) == set(SectionSlug)


@pytest.mark.parametrize(
    ("slug", "patch_target", "input_kwargs", "expected_call"),
    [
        (
            SectionSlug.SAFETY_MODERATION,
            "src.dbos_workflows.url_scan_workflow.run_safety_moderation",
            {"utterances": [_utterance()], "moderation_service": "svc"},
            {"args": [[_utterance()]], "kwargs": {"moderation_service": "svc"}},
        ),
        (
            SectionSlug.SAFETY_WEB_RISK,
            "src.dbos_workflows.url_scan_workflow.run_web_risk",
            {
                "page_url": "https://example.com",
                "mentioned_urls": ["https://a.example"],
                "media_urls": ["https://img.example"],
                "web_risk_session": "session",
                "web_risk_client": "client",
                "web_risk_lookup_cache": {"k": "v"},
            },
            {
                "args": [],
                "kwargs": {
                    "page_url": "https://example.com",
                    "mentioned_urls": ["https://a.example"],
                    "media_urls": ["https://img.example"],
                    "session": "session",
                    "web_risk_client": "client",
                    "lookup_cache": {"k": "v"},
                },
            },
        ),
        (
            SectionSlug.SAFETY_IMAGE_MODERATION,
            "src.dbos_workflows.url_scan_workflow.run_image_moderation",
            {
                "mentioned_images": ["image"],
                "image_fetch_bytes": "fetch",
                "image_safe_search": "search",
                "image_content_cache": {"k": "v"},
            },
            {
                "args": [["image"]],
                "kwargs": {
                    "fetch_bytes": "fetch",
                    "safe_search": "search",
                    "content_cache": {"k": "v"},
                },
            },
        ),
        (
            SectionSlug.SAFETY_VIDEO_MODERATION,
            "src.dbos_workflows.url_scan_workflow.run_video_moderation",
            {
                "mentioned_videos": ["video"],
                "video_sample_video": "sample",
                "video_safe_search": "search",
                "video_frame_cache": {"k": "v"},
            },
            {
                "args": [["video"]],
                "kwargs": {
                    "sample_video": "sample",
                    "safe_search": "search",
                    "frame_cache": {"k": "v"},
                },
            },
        ),
        (
            SectionSlug.TONE_DYNAMICS_FLASHPOINT,
            "src.dbos_workflows.url_scan_workflow.run_flashpoint",
            {
                "utterances": [_utterance()],
                "flashpoint_service": "svc",
                "flashpoint_max_context": 3,
                "flashpoint_score_threshold": 42,
                "flashpoint_max_concurrency": 5,
                "page_kind": PageKind.HIERARCHICAL_THREAD,
            },
            {
                "args": [[_utterance()]],
                "kwargs": {
                    "service": "svc",
                    "max_context": 3,
                    "score_threshold": 42,
                    "max_concurrency": 5,
                    "page_kind": PageKind.HIERARCHICAL_THREAD,
                },
            },
        ),
        (
            SectionSlug.TONE_DYNAMICS_SCD,
            "src.dbos_workflows.url_scan_workflow.run_scd",
            {"utterances": [_utterance()]},
            {"args": [[_utterance()]], "kwargs": {}},
        ),
        (
            SectionSlug.FACTS_CLAIMS_DEDUP,
            "src.dbos_workflows.url_scan_workflow.run_claims_dedup",
            {
                "utterances": [_utterance()],
                "claims_extract_claims": "extract",
                "claims_embed_texts": "embed",
                "claims_similarity_threshold": 0.9,
                "claims_max_concurrency": 6,
            },
            {
                "args": [[_utterance()]],
                "kwargs": {
                    "extract_claims": "extract",
                    "embed_texts": "embed",
                    "similarity_threshold": 0.9,
                    "max_concurrency": 6,
                },
            },
        ),
        (
            SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
            "src.dbos_workflows.url_scan_workflow.run_known_misinfo",
            {
                "claims_report": _claims_report(),
                "known_misinfo_lookup": "lookup",
            },
            {
                "args": [_claims_report()],
                "kwargs": {"lookup": "lookup"},
            },
        ),
        (
            SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT,
            "src.dbos_workflows.url_scan_workflow.run_sentiment",
            {
                "utterances": [_utterance()],
                "sentiment_classify_sentiment": "classifier",
                "sentiment_max_concurrency": 7,
            },
            {
                "args": [[_utterance()]],
                "kwargs": {
                    "classify_sentiment": "classifier",
                    "max_concurrency": 7,
                },
            },
        ),
        (
            SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE,
            "src.dbos_workflows.url_scan_workflow.run_subjective",
            {
                "utterances": [_utterance()],
                "subjective_extract_subjective_claims": "extractor",
                "subjective_max_concurrency": 4,
                "sentiment_stats": _sentiment_stats(),
            },
            {
                "args": [[_utterance()]],
                "kwargs": {
                    "extract_subjective_claims": "extractor",
                    "max_concurrency": 4,
                    "sentiment_stats": _sentiment_stats(),
                },
            },
        ),
    ],
)
def test_execute_url_scan_section_routes_to_expected_helper(
    slug: SectionSlug,
    patch_target: str,
    input_kwargs: dict[str, object],
    expected_call: dict[str, object],
) -> None:
    sentinel = object()

    with patch(patch_target, new=AsyncMock(return_value=sentinel)) as mock_helper:
        result = run_sync(_execute_url_scan_section(slug, UrlScanWorkflowInputs(**input_kwargs)))

    assert result is sentinel
    assert list(mock_helper.call_args.args) == expected_call["args"]
    assert mock_helper.call_args.kwargs == expected_call["kwargs"]


class TestHydrateSectionInputs:
    def test_known_misinfo_loads_claims_report_from_dedup_slot(self) -> None:
        job_id = str(uuid4())
        payload = _claims_report().model_dump(mode="json")

        with patch(
            "src.dbos_workflows.url_scan_workflow.load_url_scan_section_payload_step",
            return_value=payload,
        ) as mock_load:
            hydrated = _hydrate_section_inputs(
                job_id,
                SectionSlug.FACTS_CLAIMS_KNOWN_MISINFO,
                UrlScanWorkflowInputs(known_misinfo_lookup="lookup"),
            )

        assert hydrated.claims_report == _claims_report()
        mock_load.assert_called_once_with(job_id, SectionSlug.FACTS_CLAIMS_DEDUP.value)

    def test_subjective_loads_sentiment_stats_from_sentiment_slot(self) -> None:
        job_id = str(uuid4())
        payload = _sentiment_stats().model_dump(mode="json")

        with patch(
            "src.dbos_workflows.url_scan_workflow.load_url_scan_section_payload_step",
            return_value=payload,
        ) as mock_load:
            hydrated = _hydrate_section_inputs(
                job_id,
                SectionSlug.OPINIONS_SENTIMENTS_SUBJECTIVE,
                UrlScanWorkflowInputs(),
            )

        assert hydrated.sentiment_stats == _sentiment_stats()
        mock_load.assert_called_once_with(job_id, SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value)


class TestUrlScanSectionWorkflow:
    def test_parent_holds_token_skips_nested_gate_contention(self) -> None:
        from src.dbos_workflows.token_bucket.config import WorkflowWeight
        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            url_scan_section_workflow,
        )

        job_id = str(uuid4())
        attempt_id = str(uuid4())

        with (
            patch("src.dbos_workflows.url_scan_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.url_scan_workflow.mark_url_scan_section_running_step",
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._execute_url_scan_section",
                new=AsyncMock(return_value={"done": True}),
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow.complete_url_scan_section_step",
                return_value=True,
            ) as mock_complete,
        ):
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            result = url_scan_section_workflow.__wrapped__(  # type: ignore[attr-defined]
                job_id=job_id,
                section_slug=SectionSlug.SAFETY_MODERATION.value,
                attempt_id=attempt_id,
                section_inputs=UrlScanWorkflowInputs(),
                parent_holds_token=True,
            )

        assert result["status"] == "done"
        mock_gate_cls.assert_called_once_with(
            pool="default",
            weight=WorkflowWeight.URL_SCAN,
            parent_holds_token=True,
        )
        mock_gate.acquire.assert_called_once()
        mock_gate.release.assert_called_once()
        assert mock_complete.call_args.args[3] == {"done": True}

    def test_returns_superseded_when_running_cas_misses(self) -> None:
        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            url_scan_section_workflow,
        )

        with (
            patch("src.dbos_workflows.url_scan_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.url_scan_workflow.mark_url_scan_section_running_step",
                return_value=False,
            ),
        ):
            mock_gate_cls.return_value = MagicMock()

            result = url_scan_section_workflow.__wrapped__(  # type: ignore[attr-defined]
                job_id=str(uuid4()),
                section_slug=SectionSlug.SAFETY_MODERATION.value,
                attempt_id=str(uuid4()),
                section_inputs=UrlScanWorkflowInputs(),
            )

        assert result["status"] == "superseded"

    def test_marks_failed_and_reraises_analysis_errors(self) -> None:
        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            url_scan_section_workflow,
        )

        with (
            patch("src.dbos_workflows.url_scan_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.url_scan_workflow.mark_url_scan_section_running_step",
                return_value=True,
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._execute_url_scan_section",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow.fail_url_scan_section_step",
                return_value=True,
            ) as mock_fail,
        ):
            mock_gate_cls.return_value = MagicMock()

            with pytest.raises(RuntimeError, match="boom"):
                url_scan_section_workflow.__wrapped__(  # type: ignore[attr-defined]
                    job_id=str(uuid4()),
                    section_slug=SectionSlug.SAFETY_MODERATION.value,
                    attempt_id=str(uuid4()),
                    section_inputs=UrlScanWorkflowInputs(),
                )

        assert mock_fail.call_args.args[3] == "boom"


class TestUrlScanSectionRetryWorkflow:
    def test_rotates_only_target_slot_attempt_and_reruns_that_slot(self) -> None:
        from src.dbos_workflows.url_scan_section_retry_workflow import (
            UrlScanWorkflowInputs,
            url_scan_section_retry_workflow,
        )

        job_id = str(uuid4())
        new_attempt_id = str(uuid4())
        inputs = UrlScanWorkflowInputs()

        with (
            patch(
                "src.dbos_workflows.url_scan_section_retry_workflow.rotate_url_scan_section_attempt_step",
                return_value=new_attempt_id,
            ) as mock_rotate,
            patch(
                "src.dbos_workflows.url_scan_section_retry_workflow.url_scan_section_workflow",
                return_value={"status": "done"},
            ) as mock_section_workflow,
        ):
            result = url_scan_section_retry_workflow.__wrapped__(  # type: ignore[attr-defined]
                job_id=job_id,
                section_slug=SectionSlug.SAFETY_WEB_RISK.value,
                section_inputs=inputs,
                parent_holds_token=True,
            )

        assert result == {"status": "done"}
        mock_rotate.assert_called_once_with(job_id, SectionSlug.SAFETY_WEB_RISK.value)
        mock_section_workflow.assert_called_once_with(
            job_id=job_id,
            section_slug=SectionSlug.SAFETY_WEB_RISK.value,
            attempt_id=new_attempt_id,
            section_inputs=inputs,
            parent_holds_token=True,
        )


class TestSidebarPayloadAssembly:
    def test_builds_sidebar_payload_with_defaults_for_missing_optional_slots(self) -> None:
        utterances = [_utterance()]
        slot_payloads = {
            SectionSlug.SAFETY_MODERATION.value: {"harmful_content_matches": []},
            SectionSlug.TONE_DYNAMICS_SCD.value: _scd_report().model_dump(mode="json"),
            SectionSlug.FACTS_CLAIMS_DEDUP.value: _claims_report().model_dump(mode="json"),
            SectionSlug.OPINIONS_SENTIMENTS_SENTIMENT.value: _sentiment_stats().model_dump(
                mode="json"
            ),
        }

        payload = _build_sidebar_payload(
            source_url="https://example.com/post",
            page_title="Example",
            page_kind=PageKind.FORUM_THREAD,
            utterances=utterances,
            scraped_at="2026-05-04T12:00:00+00:00",
            slot_payloads=slot_payloads,
            recommendation_payload=_safety_recommendation().model_dump(mode="json"),
            headline_payload={"text": "A short synthesis", "kind": "synthesized"},
        )

        assert payload is not None
        assert payload.source_url == "https://example.com/post"
        assert payload.safety.recommendation == _safety_recommendation()
        assert payload.tone_dynamics.scd == _scd_report()
        assert payload.facts_claims.claims_report == _claims_report()
        assert payload.opinions_sentiments.opinions_report.sentiment_stats == _sentiment_stats()
        assert payload.web_risk.findings == []
        assert payload.image_moderation.matches == []
        assert payload.video_moderation.matches == []
        assert payload.utterances[0].position == 1
        assert payload.headline is not None
        assert payload.headline.text == "A short synthesis"

    def test_returns_none_when_required_slot_payload_is_missing(self) -> None:
        payload = _build_sidebar_payload(
            source_url="https://example.com/post",
            page_title=None,
            page_kind=PageKind.OTHER,
            utterances=[_utterance()],
            scraped_at="2026-05-04T12:00:00+00:00",
            slot_payloads={
                SectionSlug.SAFETY_MODERATION.value: {"harmful_content_matches": []},
                SectionSlug.FACTS_CLAIMS_DEDUP.value: _claims_report().model_dump(mode="json"),
            },
            recommendation_payload=None,
            headline_payload=None,
        )

        assert payload is None


class TestTerminalBatchStatus:
    @pytest.mark.parametrize(
        ("done_count", "failed_count", "expected_status"),
        [
            (10, 0, "completed"),
            (7, 3, "partial"),
            (0, 10, "failed"),
        ],
    )
    def test_maps_slot_results_to_terminal_batch_status(
        self,
        done_count: int,
        failed_count: int,
        expected_status: str,
    ) -> None:
        status = _terminal_batch_status_for_results(
            done_count=done_count,
            failed_count=failed_count,
            total_slots=len(SectionSlug),
            fatal_error_code=None,
        )

        assert status == expected_status

    def test_fatal_parent_error_forces_failed(self) -> None:
        status = _terminal_batch_status_for_results(
            done_count=9,
            failed_count=1,
            total_slots=len(SectionSlug),
            fatal_error_code="timeout",
        )

        assert status == "failed"


class TestUrlScanParentWorkflow:
    def test_parent_holds_token_and_fan_outs_then_finalizes(self) -> None:
        from src.dbos_workflows.token_bucket.config import WorkflowWeight
        from src.dbos_workflows.url_scan_workflow import (
            UrlScanWorkflowInputs,
            url_scan_orchestration_workflow,
        )

        job_id = str(uuid4())
        attempt_id = str(uuid4())
        utterances = [_utterance()]
        section_inputs = UrlScanWorkflowInputs(utterances=utterances)

        with (
            patch("src.dbos_workflows.url_scan_workflow.TokenGate") as mock_gate_cls,
            patch(
                "src.dbos_workflows.url_scan_workflow._validate_url",
                return_value={"normalized_url": "https://example.com/post", "host": "example.com"},
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._scrape",
                return_value={"scraped_at": "2026-05-04T12:00:00+00:00"},
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._extract_utterances",
                return_value={
                    "page_title": "Example",
                    "page_kind": PageKind.FORUM_THREAD.value,
                    "utterances": [item.model_dump(mode="json") for item in utterances],
                    "section_inputs": section_inputs,
                    "scraped_at": "2026-05-04T12:00:00+00:00",
                },
            ) as mock_extract,
            patch(
                "src.dbos_workflows.url_scan_workflow._fan_out_slots",
                return_value={"enqueued": len(SectionSlug)},
            ) as mock_fan_out,
            patch(
                "src.dbos_workflows.url_scan_workflow.load_url_scan_slot_results_step",
                side_effect=[
                    {"all_terminal": False},
                    {"all_terminal": True, "slots": {}, "done_count": 10, "failed_count": 0},
                ],
            ) as mock_load_slots,
            patch("src.dbos_workflows.url_scan_workflow.touch_url_scan_heartbeat_step"),
            patch("src.dbos_workflows.url_scan_workflow.DBOS.sleep") as mock_sleep,
            patch(
                "src.dbos_workflows.url_scan_workflow._run_safety_recommendation",
                return_value={"recommendation": _safety_recommendation().model_dump(mode="json")},
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._maybe_run_headline_summary",
                return_value={"headline": None},
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow._finalize",
                return_value={"status": "completed", "job_id": job_id},
            ) as mock_finalize,
        ):
            mock_gate = MagicMock()
            mock_gate_cls.return_value = mock_gate

            result = url_scan_orchestration_workflow.__wrapped__(  # type: ignore[attr-defined]
                job_id=job_id,
                source_url="https://example.com/post",
                normalized_url="https://example.com/post",
                attempt_id=attempt_id,
            )

        assert result["status"] == "completed"
        mock_gate_cls.assert_called_once_with(
            pool="default",
            weight=WorkflowWeight.URL_SCAN,
            parent_holds_token=False,
        )
        mock_gate.acquire.assert_called_once()
        mock_gate.release.assert_called_once()
        mock_extract.assert_called_once()
        mock_fan_out.assert_called_once()
        assert mock_load_slots.call_count == 2
        mock_sleep.assert_called_once()
        assert mock_finalize.call_args.kwargs["slot_results"]["done_count"] == 10


class TestDispatchUrlScanWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_existing_job_and_returns_workflow_id(self) -> None:
        from src.dbos_workflows.url_scan_workflow import dispatch_url_scan_workflow

        job_id = uuid4()
        attempt_id = uuid4()
        mock_handle = MagicMock()
        mock_handle.get_workflow_id.return_value = "url-scan-wf-123"

        with (
            patch(
                "src.dbos_workflows.url_scan_workflow.url_scan_queue.enqueue",
                return_value=mock_handle,
            ),
            patch(
                "src.dbos_workflows.url_scan_workflow.set_url_scan_workflow_id_step",
            ) as mock_set_workflow_id,
        ):
            result = await dispatch_url_scan_workflow(
                job_id=job_id,
                source_url="https://example.com/post",
                normalized_url="https://example.com/post",
                attempt_id=attempt_id,
            )

        assert result == "url-scan-wf-123"
        mock_set_workflow_id.assert_called_once_with(str(job_id), "url-scan-wf-123")

    @pytest.mark.asyncio
    async def test_uses_safe_enqueue_and_attempt_scoped_workflow_id(self) -> None:
        from src.dbos_workflows.url_scan_workflow import dispatch_url_scan_workflow

        job_id = uuid4()
        attempt_id = uuid4()

        with (
            patch(
                "src.dbos_workflows.url_scan_workflow.safe_enqueue",
                new=AsyncMock(return_value="url-scan-wf-safe"),
            ) as mock_safe_enqueue,
            patch(
                "src.dbos_workflows.url_scan_workflow.SetWorkflowID",
            ) as mock_set_workflow_id,
            patch(
                "src.dbos_workflows.url_scan_workflow.set_url_scan_workflow_id_step",
            ),
        ):
            mock_set_workflow_id.return_value.__enter__ = MagicMock(return_value=None)
            mock_set_workflow_id.return_value.__exit__ = MagicMock(return_value=False)

            result = await dispatch_url_scan_workflow(
                job_id=job_id,
                source_url="https://example.com/post",
                normalized_url="https://example.com/post",
                attempt_id=attempt_id,
            )
            enqueue_fn = mock_safe_enqueue.call_args.args[0]
            mock_handle = MagicMock()
            mock_handle.get_workflow_id.return_value = "url-scan-wf-safe"
            with patch(
                "src.dbos_workflows.url_scan_workflow.url_scan_queue.enqueue",
                return_value=mock_handle,
            ):
                assert enqueue_fn() is mock_handle

        assert result == "url-scan-wf-safe"
        mock_safe_enqueue.assert_called_once()
        mock_set_workflow_id.assert_called_once_with(f"url-scan-{job_id}-attempt-{attempt_id}")
