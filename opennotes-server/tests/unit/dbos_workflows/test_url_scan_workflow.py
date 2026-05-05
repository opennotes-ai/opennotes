from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.url_scan_workflow import (
    UrlScanWorkflowInputs,
    _execute_url_scan_section,
    _hydrate_section_inputs,
)
from src.url_content_scan.claims_schemas import ClaimsReport
from src.url_content_scan.opinions_schemas import SentimentStatsReport
from src.url_content_scan.schemas import PageKind, SectionSlug
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
