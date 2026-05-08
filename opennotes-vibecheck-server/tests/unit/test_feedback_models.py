import uuid

import pytest
from pydantic import ValidationError

from src.routes.feedback_models import (
    FeedbackCombinedRequest,
    FeedbackOpenRequest,
    FeedbackOpenResponse,
    FeedbackSubmitRequest,
)


def test_open_request_validates_with_valid_data():
    req = FeedbackOpenRequest(
        kind="open",
        page_path="/dashboard",
        user_agent="Mozilla/5.0",
        bell_location="bottom-right",
        initial_type="thumbs_up",
    )
    assert req.page_path == "/dashboard"
    assert req.initial_type == "thumbs_up"
    assert req.referrer == ""
    assert req.kind == "open"


def test_open_request_rejects_invalid_initial_type():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackOpenRequest(
            kind="open",
            page_path="/dashboard",
            user_agent="Mozilla/5.0",
            bell_location="bottom-right",
            initial_type="lol",
        )
    errors = exc_info.value.errors()
    field_paths = [e["loc"] for e in errors]
    assert ("initial_type",) in field_paths


def test_open_request_rejects_unknown_extra_field():
    with pytest.raises(ValidationError):
        FeedbackOpenRequest(
            kind="open",
            page_path="/dashboard",
            user_agent="Mozilla/5.0",
            bell_location="bottom-right",
            initial_type="thumbs_up",
            mystery_field="surprise",
        )


def test_combined_request_rejects_unknown_extra_field():
    with pytest.raises(ValidationError):
        FeedbackCombinedRequest(
            kind="combined",
            page_path="/home",
            user_agent="Mozilla/5.0",
            bell_location="top-left",
            initial_type="thumbs_down",
            final_type="thumbs_down",
            mystery_field="surprise",
        )


def test_submit_request_rejects_unknown_extra_field():
    with pytest.raises(ValidationError):
        FeedbackSubmitRequest(
            final_type="thumbs_up",
            mystery_field="surprise",
        )


def test_combined_request_rejects_message_longer_than_4000_chars():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackCombinedRequest(
            kind="combined",
            page_path="/home",
            user_agent="Mozilla/5.0",
            bell_location="top-left",
            initial_type="message",
            final_type="message",
            message="x" * 4001,
        )
    field_paths = [e["loc"] for e in exc_info.value.errors()]
    assert ("message",) in field_paths


def test_submit_request_rejects_message_longer_than_4000_chars():
    with pytest.raises(ValidationError) as exc_info:
        FeedbackSubmitRequest(
            final_type="message",
            message="x" * 4001,
        )
    field_paths = [e["loc"] for e in exc_info.value.errors()]
    assert ("message",) in field_paths


def test_combined_request_accepts_message_at_exactly_4000_chars():
    req = FeedbackCombinedRequest(
        kind="combined",
        page_path="/home",
        user_agent="Mozilla/5.0",
        bell_location="top-left",
        initial_type="message",
        final_type="message",
        message="x" * 4000,
    )
    assert req.message is not None and len(req.message) == 4000


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


def test_combined_request_accepts_both_initial_and_final_types():
    req = FeedbackCombinedRequest(
        kind="combined",
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
    assert req.kind == "combined"


def test_open_response_holds_uuid():
    session_id = uuid.uuid4()
    resp = FeedbackOpenResponse(id=session_id)
    assert resp.id == session_id
