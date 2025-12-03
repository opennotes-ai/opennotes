import pytest
from pydantic import ValidationError

from src.community_config.router import MAX_KEY_LENGTH, MAX_VALUE_LENGTH, SetConfigRequest


@pytest.mark.unit
class TestSetConfigRequestValidation:
    def test_valid_config_key_simple(self):
        request = SetConfigRequest(key="notes_enabled", value="true")
        assert request.key == "notes_enabled"
        assert request.value == "true"

    def test_valid_config_key_with_numbers(self):
        request = SetConfigRequest(key="rate_limit_5", value="100")
        assert request.key == "rate_limit_5"

    def test_valid_config_key_multiple_underscores(self):
        request = SetConfigRequest(key="notify_note_helpful", value="false")
        assert request.key == "notify_note_helpful"

    def test_valid_value_empty_string(self):
        request = SetConfigRequest(key="test_key", value="")
        assert request.value == ""

    def test_valid_value_max_length(self):
        max_value = "x" * MAX_VALUE_LENGTH
        request = SetConfigRequest(key="test_key", value=max_value)
        assert len(request.value) == MAX_VALUE_LENGTH

    def test_invalid_key_empty_string(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="", value="test")
        errors = exc_info.value.errors()
        assert any("at least 1 character" in str(err) for err in errors)

    def test_invalid_key_starts_with_number(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="5_rate_limit", value="100")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_starts_with_underscore(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="_notes_enabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_uppercase_letters(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="NotesEnabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_camel_case(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="notesEnabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_with_hyphen(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="notes-enabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_with_space(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="notes enabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_with_special_chars(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="notes@enabled", value="true")
        errors = exc_info.value.errors()
        assert any(
            "pattern" in str(err).lower() or "string_pattern_mismatch" in str(err) for err in errors
        )

    def test_invalid_key_exceeds_max_length(self):
        long_key = "a" * (MAX_KEY_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key=long_key, value="test")
        errors = exc_info.value.errors()
        assert any("at most 128 characters" in str(err) for err in errors)

    def test_valid_key_at_max_length(self):
        max_key = "a" * MAX_KEY_LENGTH
        request = SetConfigRequest(key=max_key, value="test")
        assert len(request.key) == MAX_KEY_LENGTH

    def test_invalid_value_exceeds_max_length(self):
        long_value = "x" * (MAX_VALUE_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value=long_value)
        errors = exc_info.value.errors()
        assert any("at most 10240 characters" in str(err) for err in errors)

    def test_valid_value_with_json(self):
        # Note: JSON values with quotes are now rejected for security
        # Use a generic key that doesn't trigger type-based validation
        # and avoid dangerous characters like quotes
        request = SetConfigRequest(key="config_json", value="{enabled: true, limit: 5}")
        assert request.value == "{enabled: true, limit: 5}"

    def test_valid_value_with_newlines(self):
        request = SetConfigRequest(key="multiline_config", value="line1\nline2\nline3")
        assert "\n" in request.value

    def test_valid_value_with_unicode(self):
        request = SetConfigRequest(key="unicode_test", value="Hello 世界 🌍")
        assert request.value == "Hello 世界 🌍"

    def test_error_message_clarity_for_pattern_violation(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="Invalid-Key", value="test")
        errors = exc_info.value.errors()
        error_msg = str(errors[0])
        assert "pattern" in error_msg.lower() or "string_pattern_mismatch" in error_msg
        assert "^[a-z][a-z0-9_]*$" in error_msg

    def test_boundary_key_single_char(self):
        request = SetConfigRequest(key="a", value="test")
        assert request.key == "a"

    def test_boundary_key_two_chars(self):
        request = SetConfigRequest(key="ab", value="test")
        assert request.key == "ab"

    def test_boundary_value_single_char(self):
        request = SetConfigRequest(key="test_key", value="x")
        assert request.value == "x"

    def test_boundary_value_near_max(self):
        near_max_value = "x" * (MAX_VALUE_LENGTH - 1)
        request = SetConfigRequest(key="test_key", value=near_max_value)
        assert len(request.value) == MAX_VALUE_LENGTH - 1

    def test_multiple_validation_errors(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="", value="x" * (MAX_VALUE_LENGTH + 1))
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_valid_known_config_keys(self):
        # Map keys to appropriate values based on their type
        known_keys_with_values = [
            ("request_note_ephemeral", "true"),  # boolean
            ("write_note_ephemeral", "false"),  # boolean
            ("rate_note_ephemeral", "true"),  # boolean
            ("list_requests_ephemeral", "false"),  # boolean
            ("status_ephemeral", "true"),  # boolean
            ("notes_enabled", "true"),  # boolean
            ("ratings_enabled", "false"),  # boolean
            ("requests_enabled", "true"),  # boolean
            ("note_rate_limit", "100"),  # numeric (contains "limit")
            ("rating_rate_limit", "50"),  # numeric (contains "limit")
            ("request_rate_limit", "25"),  # numeric (contains "limit")
            (
                "notify_note_helpful",
                "true",
            ),  # boolean (notify... doesn't trigger, so any safe value works)
            (
                "notify_request_fulfilled",
                "false",
            ),  # boolean (notify... doesn't trigger, so any safe value works)
        ]
        for key, value in known_keys_with_values:
            request = SetConfigRequest(key=key, value=value)
            assert request.key == key
            assert request.value == value


@pytest.mark.unit
class TestSetConfigRequestValueSanitization:
    """Tests for value sanitization and injection prevention"""

    def test_reject_value_with_script_tags(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="<script>alert('xss')</script>")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_html_tags(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="<div>content</div>")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_double_quotes(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value='value with "quotes"')
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_single_quotes(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value with 'quotes'")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_backticks(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value with `backticks`")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_dollar_sign(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value with $variable")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_semicolon(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value; drop table;")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_pipe(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value | command")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_ampersand(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value && command")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_reject_value_with_null_byte(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="test_key", value="value\x00null")
        errors = exc_info.value.errors()
        assert any("unsafe characters" in str(err).lower() for err in errors)

    def test_accept_value_with_safe_characters(self):
        safe_values = [
            "simple_value",
            "value-with-hyphens",
            "value.with.dots",
            "value_123",
            "CamelCaseValue",
            "value with spaces",
            "value:with:colons",
            "value@with@at",
            "value/with/slashes",
            "value+with+plus",
            "value=with=equals",
        ]
        for value in safe_values:
            request = SetConfigRequest(key="test_key", value=value)
            assert request.value == value


@pytest.mark.unit
class TestSetConfigRequestTypeBasedValidation:
    """Tests for type-based validation based on config key patterns"""

    # Numeric validation tests
    def test_rate_limit_accepts_valid_number(self):
        request = SetConfigRequest(key="rate_limit_per_hour", value="100")
        assert request.value == "100"

    def test_rate_limit_rejects_non_numeric(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="rate_limit_per_hour", value="not_a_number")
        errors = exc_info.value.errors()
        assert any("numeric value" in str(err).lower() for err in errors)

    def test_rate_limit_rejects_negative(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="rate_limit_per_hour", value="-100")
        errors = exc_info.value.errors()
        assert any(
            "non-negative" in str(err).lower() or "numeric value" in str(err).lower()
            for err in errors
        )

    def test_rate_limit_rejects_too_large(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="rate_limit_per_hour", value="2000000")
        errors = exc_info.value.errors()
        assert any("too large" in str(err).lower() for err in errors)

    def test_max_count_accepts_valid_number(self):
        request = SetConfigRequest(key="max_notes_per_user", value="50")
        assert request.value == "50"

    def test_threshold_accepts_zero(self):
        request = SetConfigRequest(key="min_rating_threshold", value="0")
        assert request.value == "0"

    def test_timeout_accepts_valid_number(self):
        request = SetConfigRequest(key="session_timeout", value="3600")
        assert request.value == "3600"

    # Boolean validation tests
    def test_enabled_accepts_true(self):
        request = SetConfigRequest(key="notes_enabled", value="true")
        assert request.value == "true"

    def test_enabled_accepts_false(self):
        request = SetConfigRequest(key="notes_enabled", value="false")
        assert request.value == "false"

    def test_enabled_accepts_1(self):
        request = SetConfigRequest(key="notes_enabled", value="1")
        assert request.value == "1"

    def test_enabled_accepts_0(self):
        request = SetConfigRequest(key="notes_enabled", value="0")
        assert request.value == "0"

    def test_enabled_accepts_yes(self):
        request = SetConfigRequest(key="notes_enabled", value="yes")
        assert request.value == "yes"

    def test_enabled_accepts_no(self):
        request = SetConfigRequest(key="notes_enabled", value="no")
        assert request.value == "no"

    def test_enabled_accepts_case_insensitive(self):
        request = SetConfigRequest(key="notes_enabled", value="True")
        assert request.value == "True"

    def test_enabled_rejects_invalid_boolean(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="notes_enabled", value="maybe")
        errors = exc_info.value.errors()
        assert any("boolean value" in str(err).lower() for err in errors)

    def test_active_flag_accepts_boolean(self):
        request = SetConfigRequest(key="feature_active", value="true")
        assert request.value == "true"

    def test_allow_flag_accepts_boolean(self):
        request = SetConfigRequest(key="allow_anonymous", value="false")
        assert request.value == "false"

    # URL validation tests
    def test_webhook_url_accepts_https(self):
        request = SetConfigRequest(key="webhook_url", value="https://example.com/webhook")
        assert request.value == "https://example.com/webhook"

    def test_webhook_url_accepts_http(self):
        request = SetConfigRequest(key="webhook_url", value="http://localhost:8000/webhook")
        assert request.value == "http://localhost:8000/webhook"

    def test_webhook_url_rejects_invalid_protocol(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="webhook_url", value="ftp://example.com")
        errors = exc_info.value.errors()
        assert any("valid url" in str(err).lower() for err in errors)

    def test_webhook_url_rejects_no_protocol(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="webhook_url", value="example.com/webhook")
        errors = exc_info.value.errors()
        assert any("valid url" in str(err).lower() for err in errors)

    def test_webhook_url_rejects_whitespace(self):
        with pytest.raises(ValidationError) as exc_info:
            SetConfigRequest(key="webhook_url", value="https://example.com /webhook")
        errors = exc_info.value.errors()
        assert any("whitespace" in str(err).lower() for err in errors)

    def test_endpoint_url_validates(self):
        request = SetConfigRequest(
            key="notification_endpoint", value="https://api.example.com/notify"
        )
        assert request.value == "https://api.example.com/notify"

    # Test non-specific keys accept any safe value
    def test_generic_key_accepts_text(self):
        request = SetConfigRequest(key="custom_message", value="Welcome to our community")
        assert request.value == "Welcome to our community"

    def test_generic_key_accepts_numbers(self):
        request = SetConfigRequest(key="custom_value", value="12345")
        assert request.value == "12345"
