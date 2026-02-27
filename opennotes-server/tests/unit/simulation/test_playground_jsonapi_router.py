from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.simulation.schemas import (
    PlaygroundNoteRequestAttributes,
    PlaygroundNoteRequestBody,
    PlaygroundNoteRequestData,
    PlaygroundNoteRequestJobAttributes,
    PlaygroundNoteRequestJobResource,
    PlaygroundNoteRequestJobResponse,
    PlaygroundNoteRequestListResponse,
    PlaygroundNoteRequestResultAttributes,
    PlaygroundNoteRequestResultResource,
)


@pytest.mark.unit
class TestPlaygroundNoteRequestAttributes:
    def test_valid_single_url(self):
        attrs = PlaygroundNoteRequestAttributes(urls=["https://example.com/article"])
        assert len(attrs.urls) == 1
        assert str(attrs.urls[0]) == "https://example.com/article"

    def test_valid_multiple_urls(self):
        urls = [f"https://example.com/article{i}" for i in range(5)]
        attrs = PlaygroundNoteRequestAttributes(urls=urls)
        assert len(attrs.urls) == 5

    def test_max_20_urls(self):
        urls = [f"https://example.com/article{i}" for i in range(20)]
        attrs = PlaygroundNoteRequestAttributes(urls=urls)
        assert len(attrs.urls) == 20

    def test_rejects_more_than_20_urls(self):
        urls = [f"https://example.com/article{i}" for i in range(21)]
        with pytest.raises(ValidationError, match="at most 20"):
            PlaygroundNoteRequestAttributes(urls=urls)

    def test_rejects_empty_url_list(self):
        with pytest.raises(ValidationError, match="At least one of"):
            PlaygroundNoteRequestAttributes(urls=[])

    def test_rejects_invalid_url(self):
        with pytest.raises(ValidationError):
            PlaygroundNoteRequestAttributes(urls=["not-a-url"])

    def test_default_requested_by(self):
        attrs = PlaygroundNoteRequestAttributes(urls=["https://example.com"])
        assert attrs.requested_by == "system-playground"

    def test_custom_requested_by(self):
        attrs = PlaygroundNoteRequestAttributes(
            urls=["https://example.com"], requested_by="custom-user"
        )
        assert attrs.requested_by == "custom-user"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            PlaygroundNoteRequestAttributes(urls=["https://example.com"], unknown_field="value")


@pytest.mark.unit
class TestPlaygroundNoteRequestBody:
    def test_valid_body(self):
        body = PlaygroundNoteRequestBody(
            data=PlaygroundNoteRequestData(
                type="playground-note-requests",
                attributes=PlaygroundNoteRequestAttributes(urls=["https://example.com/article"]),
            )
        )
        assert body.data.type == "playground-note-requests"
        assert len(body.data.attributes.urls) == 1

    def test_rejects_wrong_type(self):
        with pytest.raises(ValidationError, match="playground-note-requests"):
            PlaygroundNoteRequestBody(
                data=PlaygroundNoteRequestData(
                    type="wrong-type",
                    attributes=PlaygroundNoteRequestAttributes(urls=["https://example.com"]),
                )
            )

    def test_rejects_extra_fields_in_data(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            PlaygroundNoteRequestBody(
                data={
                    "type": "playground-note-requests",
                    "attributes": {"urls": ["https://example.com"]},
                    "extra_field": "bad",
                }
            )

    def test_rejects_extra_fields_in_body(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            PlaygroundNoteRequestBody(
                data={
                    "type": "playground-note-requests",
                    "attributes": {"urls": ["https://example.com"]},
                },
                extra="bad",
            )

    def test_from_dict(self):
        body = PlaygroundNoteRequestBody.model_validate(
            {
                "data": {
                    "type": "playground-note-requests",
                    "attributes": {
                        "urls": [
                            "https://example.com/article1",
                            "https://example.com/article2",
                        ],
                        "requested_by": "test-user",
                    },
                }
            }
        )
        assert len(body.data.attributes.urls) == 2
        assert body.data.attributes.requested_by == "test-user"


@pytest.mark.unit
class TestPlaygroundNoteRequestResultAttributes:
    def test_valid_result_attributes(self):
        attrs = PlaygroundNoteRequestResultAttributes(
            request_id="playground-abc123",
            requested_by="system-playground",
            status="PENDING",
            community_server_id=str(uuid4()),
            content="Extracted content here",
            url="https://example.com/article",
        )
        assert attrs.request_id == "playground-abc123"
        assert attrs.status == "PENDING"
        assert attrs.error is None

    def test_failed_result_with_error(self):
        attrs = PlaygroundNoteRequestResultAttributes(
            request_id="playground-abc123",
            requested_by="system-playground",
            status="FAILED",
            community_server_id=str(uuid4()),
            url="https://example.com/article",
            error="Failed to extract content",
        )
        assert attrs.status == "FAILED"
        assert attrs.error == "Failed to extract content"
        assert attrs.content is None


@pytest.mark.unit
class TestPlaygroundNoteRequestListResponse:
    def test_valid_response(self):
        cs_id = str(uuid4())
        response = PlaygroundNoteRequestListResponse(
            data=[
                PlaygroundNoteRequestResultResource(
                    type="requests",
                    id=str(uuid4()),
                    attributes=PlaygroundNoteRequestResultAttributes(
                        request_id="playground-abc123",
                        requested_by="system-playground",
                        status="PENDING",
                        community_server_id=cs_id,
                        content="Some content",
                        url="https://example.com",
                    ),
                )
            ],
            meta={"count": 1, "succeeded": 1, "failed": 0},
        )
        assert len(response.data) == 1
        assert response.jsonapi == {"version": "1.1"}
        assert response.meta["count"] == 1

    def test_empty_response(self):
        response = PlaygroundNoteRequestListResponse(
            data=[],
            meta={"count": 0, "succeeded": 0, "failed": 0},
        )
        assert len(response.data) == 0

    def test_serialization(self):
        cs_id = str(uuid4())
        req_id = str(uuid4())
        response = PlaygroundNoteRequestListResponse(
            data=[
                PlaygroundNoteRequestResultResource(
                    type="requests",
                    id=req_id,
                    attributes=PlaygroundNoteRequestResultAttributes(
                        request_id="playground-abc123",
                        requested_by="system-playground",
                        status="PENDING",
                        community_server_id=cs_id,
                        url="https://example.com",
                    ),
                )
            ],
            meta={"count": 1, "succeeded": 1, "failed": 0},
        )
        dumped = response.model_dump(by_alias=True, mode="json")
        assert dumped["jsonapi"]["version"] == "1.1"
        assert dumped["data"][0]["type"] == "requests"
        assert dumped["data"][0]["id"] == req_id


@pytest.mark.unit
class TestPlaygroundNoteRequestJobResponse:
    def test_valid_job_response(self):
        wf_id = "playground-urls-abc123"
        response = PlaygroundNoteRequestJobResponse(
            data=PlaygroundNoteRequestJobResource(
                id=wf_id,
                attributes=PlaygroundNoteRequestJobAttributes(
                    workflow_id=wf_id,
                    url_count=5,
                ),
            ),
        )
        assert response.data.id == wf_id
        assert response.data.type == "playground-note-request-jobs"
        assert response.data.attributes.workflow_id == wf_id
        assert response.data.attributes.url_count == 5
        assert response.data.attributes.status == "ACCEPTED"
        assert response.jsonapi == {"version": "1.1"}

    def test_job_response_serialization(self):
        wf_id = "playground-urls-def456"
        response = PlaygroundNoteRequestJobResponse(
            data=PlaygroundNoteRequestJobResource(
                id=wf_id,
                attributes=PlaygroundNoteRequestJobAttributes(
                    workflow_id=wf_id,
                    url_count=3,
                ),
            ),
        )
        dumped = response.model_dump(by_alias=True, mode="json")
        assert dumped["jsonapi"]["version"] == "1.1"
        assert dumped["data"]["type"] == "playground-note-request-jobs"
        assert dumped["data"]["id"] == wf_id
        assert dumped["data"]["attributes"]["workflow_id"] == wf_id
        assert dumped["data"]["attributes"]["url_count"] == 3
        assert dumped["data"]["attributes"]["status"] == "ACCEPTED"
