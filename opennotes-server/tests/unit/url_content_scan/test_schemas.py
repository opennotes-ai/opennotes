from datetime import UTC, datetime
from importlib import import_module
from uuid import uuid4

import pytest


def _load_schemas_module():
    return import_module("src.url_content_scan.schemas")


def _load_router_module():
    return import_module("src.url_content_scan.router")


def _empty_sidebar_payload(schemas_module, scraped_at: datetime):
    return schemas_module.SidebarPayload.model_validate(
        {
            "source_url": "https://example.com",
            "scraped_at": scraped_at.isoformat(),
            "page_kind": "other",
            "safety": {"harmful_content_matches": []},
            "tone_dynamics": {
                "scd": {
                    "narrative": "",
                    "speaker_arcs": [],
                    "summary": "",
                    "tone_labels": [],
                    "per_speaker_notes": {},
                    "insufficient_conversation": True,
                },
                "flashpoint_matches": [],
            },
            "facts_claims": {
                "claims_report": {
                    "deduped_claims": [],
                    "total_claims": 0,
                    "total_unique": 0,
                },
                "known_misinformation": [],
            },
            "opinions_sentiments": {
                "opinions_report": {
                    "sentiment_stats": {
                        "per_utterance": [],
                        "positive_pct": 0.0,
                        "negative_pct": 0.0,
                        "neutral_pct": 0.0,
                        "mean_valence": 0.0,
                    },
                    "subjective_claims": [],
                }
            },
            "utterances": [{"position": 1, "utterance_id": "u-1"}],
        }
    )


@pytest.mark.unit
def test_section_slug_matches_vibecheck_wire_contract():
    schemas = _load_schemas_module()

    assert [slug.value for slug in schemas.SectionSlug] == [
        "safety__moderation",
        "safety__web_risk",
        "safety__image_moderation",
        "safety__video_moderation",
        "tone_dynamics__flashpoint",
        "tone_dynamics__scd",
        "facts_claims__dedup",
        "facts_claims__known_misinfo",
        "opinions_sentiments__sentiment",
        "opinions_sentiments__subjective",
    ]
    assert len(list(schemas.SectionSlug)) == 10
    assert "recommendation_agent" not in {slug.value for slug in schemas.SectionSlug}


@pytest.mark.unit
def test_job_status_stays_on_wire_enum_only():
    schemas = _load_schemas_module()

    assert [status.value for status in schemas.JobStatus] == [
        "pending",
        "extracting",
        "analyzing",
        "done",
        "partial",
        "failed",
    ]


@pytest.mark.unit
def test_job_state_and_sidebar_payload_accept_vibecheck_shape():
    schemas = _load_schemas_module()
    now = datetime.now(UTC)
    sidebar_payload = _empty_sidebar_payload(schemas, now)

    job = schemas.JobState.model_validate(
        {
            "job_id": str(uuid4()),
            "url": "https://example.com",
            "status": "done",
            "attempt_id": str(uuid4()),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "sections": {
                "safety__moderation": {
                    "state": "done",
                    "attempt_id": str(uuid4()),
                    "data": {"harmful_content_matches": []},
                    "finished_at": now.isoformat(),
                }
            },
            "sidebar_payload": sidebar_payload.model_dump(mode="json"),
            "sidebar_payload_complete": True,
            "page_title": "Example",
            "page_kind": "article",
            "utterance_count": 2,
        }
    )

    assert job.status is schemas.JobStatus.DONE
    assert job.sections[schemas.SectionSlug.SAFETY_MODERATION].state is schemas.SectionState.DONE
    assert job.sidebar_payload is not None
    assert job.sidebar_payload.utterances[0].utterance_id == "u-1"
    assert job.sidebar_payload_complete is True


@pytest.mark.unit
def test_router_scaffold_uses_expected_prefix_and_tag():
    router_module = _load_router_module()

    assert router_module.router.prefix == "/api/v1/url_scan"
    assert router_module.router.tags == ["url_scan"]
    assert [route.path for route in router_module.router.routes] == [
        "/api/v1/url_scan/_schema_anchor",
        "/api/v1/url_scan/_sidebar_schema_anchor",
    ]


@pytest.mark.unit
def test_router_openapi_anchor_emits_url_scan_components():
    router_module = _load_router_module()

    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router_module.router)

    schema = test_app.openapi()
    components = schema["components"]["schemas"]

    assert "/api/v1/url_scan/_schema_anchor" in schema["paths"]
    assert "/api/v1/url_scan/_sidebar_schema_anchor" in schema["paths"]
    assert "JobState" in components
    assert "SidebarPayload" in components
    assert "SectionSlot" in components
    assert "ErrorCode" in components
    assert "UtteranceAnchor" in components
