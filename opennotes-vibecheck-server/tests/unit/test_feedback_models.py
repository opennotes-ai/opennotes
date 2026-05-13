import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from src.routes.feedback_models import (
    FeedbackCombinedRequest,
    FeedbackOpenRequest,
    FeedbackOpenResponse,
    FeedbackRequest,
    FeedbackSubmitRequest,
)

_adapter = TypeAdapter(FeedbackRequest)


def test_open_request_validates_with_valid_data():
    req = FeedbackOpenRequest(
        page_path="/dashboard",
        user_agent="Mozilla/5.0",
        bell_location="bottom-right",
        initial_type="thumbs_up",
    )
    assert req.page_path == "/dashboard"
    assert req.initial_type == "thumbs_up"
    assert req.referrer == ""


def test_open_request_rejects_invalid_initial_type():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackOpenRequest.model_validate(
            {
                "page_path": "/dashboard",
                "user_agent": "Mozilla/5.0",
                "bell_location": "bottom-right",
                "initial_type": "lol",
            }
        )
    errors = exc_info.value.errors()
    field_paths = [e["loc"] for e in errors]
    assert ("initial_type",) in field_paths


def test_open_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        FeedbackOpenRequest.model_validate(
            {
                "page_path": "/dashboard",
                "user_agent": "Mozilla/5.0",
                "bell_location": "bottom-right",
                "initial_type": "thumbs_up",
                "unknown_extra_field": "should_be_rejected",
            }
        )


def test_submit_request_rejects_invalid_email():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackSubmitRequest(
            email="not-an-email",
            final_type="thumbs_down",
        )
    errors = exc_info.value.errors()
    field_paths = [e["loc"] for e in errors]
    assert ("email",) in field_paths


def test_submit_request_allows_null_email_and_message_for_thumbs_up():
    req = FeedbackSubmitRequest(
        email=None,
        message=None,
        final_type="thumbs_up",
    )
    assert req.email is None
    assert req.message is None
    assert req.final_type == "thumbs_up"


def test_submit_request_rejects_message_over_4000_chars():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackSubmitRequest(
            final_type="message",
            message="x" * 4001,
        )
    errors = exc_info.value.errors()
    field_paths = [e["loc"] for e in errors]
    assert ("message",) in field_paths


def test_combined_request_accepts_both_initial_and_final_types():
    req = FeedbackCombinedRequest(
        page_path="/home",
        user_agent="Mozilla/5.0",
        bell_location="top-left",
        initial_type="thumbs_down",
        final_type="message",
        message="Something felt off",
        email="user@example.com",
    )
    assert req.initial_type == "thumbs_down"
    assert req.final_type == "message"
    assert req.message == "Something felt off"
    assert str(req.email) == "user@example.com"


def test_combined_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        FeedbackCombinedRequest.model_validate(
            {
                "page_path": "/home",
                "user_agent": "Mozilla/5.0",
                "bell_location": "top-left",
                "initial_type": "thumbs_down",
                "final_type": "message",
                "unknown_extra_field": "should_be_rejected",
            }
        )


def test_open_response_holds_uuid():
    session_id = uuid.uuid4()
    resp = FeedbackOpenResponse(id=session_id)
    assert resp.id == session_id


def test_feedback_request_infers_open_when_no_final_type():
    req = _adapter.validate_python(
        {
            "page_path": "/analyze",
            "user_agent": "Mozilla/5.0",
            "bell_location": "bottom-right",
            "initial_type": "thumbs_up",
        }
    )
    assert isinstance(req, FeedbackOpenRequest)
    assert req.kind == "open"


def test_feedback_request_infers_combined_when_final_type_present():
    req = _adapter.validate_python(
        {
            "page_path": "/analyze",
            "user_agent": "Mozilla/5.0",
            "bell_location": "bottom-right",
            "initial_type": "thumbs_up",
            "final_type": "thumbs_up",
        }
    )
    assert isinstance(req, FeedbackCombinedRequest)
    assert req.kind == "combined"


def test_feedback_request_explicit_kind_open_overrides_inference():
    req = _adapter.validate_python(
        {
            "kind": "open",
            "page_path": "/analyze",
            "user_agent": "Mozilla/5.0",
            "bell_location": "bottom-right",
            "initial_type": "thumbs_up",
        }
    )
    assert isinstance(req, FeedbackOpenRequest)
    assert req.kind == "open"


def test_feedback_request_explicit_kind_combined():
    req = _adapter.validate_python(
        {
            "kind": "combined",
            "page_path": "/analyze",
            "user_agent": "Mozilla/5.0",
            "bell_location": "bottom-right",
            "initial_type": "thumbs_up",
            "final_type": "thumbs_down",
            "message": "Nice!",
        }
    )
    assert isinstance(req, FeedbackCombinedRequest)


def test_feedback_request_combined_missing_final_type_raises_422():
    with pytest.raises(ValidationError):
        _adapter.validate_python(
            {
                "kind": "combined",
                "page_path": "/analyze",
                "user_agent": "Mozilla/5.0",
                "bell_location": "bottom-right",
                "initial_type": "thumbs_up",
            }
        )


def test_combined_request_rejects_message_over_4000_chars():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackCombinedRequest(
            page_path="/home",
            user_agent="Mozilla/5.0",
            bell_location="top-left",
            initial_type="thumbs_down",
            final_type="message",
            message="x" * 4001,
        )
    errors = exc_info.value.errors()
    field_paths = [e["loc"] for e in errors]
    assert ("message",) in field_paths
