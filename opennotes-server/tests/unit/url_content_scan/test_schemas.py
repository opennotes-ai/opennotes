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

    slug_values = [slug.value for slug in schemas.SectionSlug]
    assert "safety__moderation" in slug_values
    assert "safety__web_risk" in slug_values
    assert "safety__image_moderation" in slug_values
    assert "safety__video_moderation" in slug_values
    assert "tone_dynamics__flashpoint" in slug_values
    assert "tone_dynamics__scd" in slug_values
    assert "facts_claims__dedup" in slug_values
    assert "facts_claims__known_misinfo" in slug_values
    assert "opinions_sentiments__sentiment" in slug_values
    assert "opinions_sentiments__subjective" in slug_values
    assert "recommendation_agent" not in slug_values


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
    assert {route.path for route in router_module.router.routes} >= {
        "/api/v1/url_scan/analyze",
        "/api/v1/url_scan/embed/v1/start",
        "/api/v1/url_scan/jobs/{job_id}",
        "/api/v1/url_scan/jobs/{job_id}/retry/{slug}",
        "/api/v1/url_scan/analyses/recent",
        "/api/v1/url_scan/frame-compat",
        "/api/v1/url_scan/screenshot",
        "/api/v1/url_scan/archive-preview",
        "/api/v1/url_scan/_schema_anchor",
        "/api/v1/url_scan/_sidebar_schema_anchor",
    }


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
    archive_response = schema["paths"]["/api/v1/url_scan/archive-preview"]["get"]["responses"][
        "200"
    ]
    assert "text/html" in archive_response["content"]
    assert "JobState" in components
    assert "SidebarPayload" in components
    assert "SectionSlot" in components
    assert "ErrorCode" in components
    assert "UtteranceAnchor" in components


@pytest.mark.unit
def test_sidebar_payload_does_not_carry_page_metadata():
    schemas = _load_schemas_module()
    sidebar_fields = schemas.SidebarPayload.model_fields
    assert "source_url" not in sidebar_fields, "source_url moved to url_scan_state column"
    assert "page_title" not in sidebar_fields, "page_title moved to url_scan_state column"
    assert "page_kind" not in sidebar_fields, "page_kind moved to url_scan_state column"


@pytest.mark.unit
def test_job_state_carries_page_metadata_as_top_level_fields():
    schemas = _load_schemas_module()
    job_fields = schemas.JobState.model_fields
    assert "page_title" in job_fields
    assert "page_kind" in job_fields


@pytest.mark.unit
def test_sidebar_payload_accepts_data_without_page_metadata():
    schemas = _load_schemas_module()
    now = datetime.now(UTC)
    payload = schemas.SidebarPayload.model_validate(
        {
            "scraped_at": now.isoformat(),
            "safety": {"harmful_content_matches": []},
            "tone_dynamics": {
                "scd": {
                    "summary": "",
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
        }
    )
    assert payload.scraped_at is not None
