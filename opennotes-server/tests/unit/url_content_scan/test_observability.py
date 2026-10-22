from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.url_content_scan.observability import (
    URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS,
    _sanitize_value,
    url_scan_extractor_instrumentation,
    url_scan_instrumentation,
)


class _MockSettings:
    URL_SCAN_LOGFIRE_CONTENT: bool = False
    URL_SCAN_EXTRACTOR_SAMPLE_RATE: float = 0.05


class _MockSettingsContentOn:
    URL_SCAN_LOGFIRE_CONTENT: bool = True
    URL_SCAN_EXTRACTOR_SAMPLE_RATE: float = 0.05


def test_url_scan_instrumentation_content_off_by_default():
    settings = _MockSettings()
    result = url_scan_instrumentation(settings)
    assert result.settings.include_content is False
    assert result.settings.include_binary_content is False


def test_url_scan_instrumentation_content_on_when_setting_true():
    settings = _MockSettingsContentOn()
    result = url_scan_instrumentation(settings)
    assert result.settings.include_content is True
    assert result.settings.include_binary_content is False


def test_url_scan_instrumentation_no_settings_defaults_false():
    result = url_scan_instrumentation()
    assert result.settings.include_content is False
    assert result.settings.include_binary_content is False


def test_url_scan_extractor_instrumentation_rate_zero_always_false():
    mock_settings = MagicMock()
    mock_settings.URL_SCAN_EXTRACTOR_SAMPLE_RATE = 0.0
    for _ in range(20):
        result = url_scan_extractor_instrumentation(mock_settings)
        assert result.include_content is False


def test_url_scan_extractor_instrumentation_rate_one_always_true():
    mock_settings = MagicMock()
    mock_settings.URL_SCAN_EXTRACTOR_SAMPLE_RATE = 1.0
    for _ in range(20):
        result = url_scan_extractor_instrumentation(mock_settings)
        assert result.include_content is True


def test_url_scan_extractor_instrumentation_sampling_honors_rate():
    mock_settings = MagicMock()
    mock_settings.URL_SCAN_EXTRACTOR_SAMPLE_RATE = 0.5

    with patch("src.url_content_scan.observability.random") as mock_random:
        mock_random.random.return_value = 0.3
        result = url_scan_extractor_instrumentation(mock_settings)
        assert result.include_content is True

        mock_random.random.return_value = 0.7
        result = url_scan_extractor_instrumentation(mock_settings)
        assert result.include_content is False


def test_url_scan_extractor_instrumentation_include_binary_always_false():
    mock_settings = MagicMock()
    mock_settings.URL_SCAN_EXTRACTOR_SAMPLE_RATE = 1.0
    result = url_scan_extractor_instrumentation(mock_settings)
    assert result.include_binary_content is False


def test_scrub_callback_rewrites_token_query_param():
    value = "https://example.com/api?token=abcdef123&other=ok"
    result = _sanitize_value(value)
    assert "abcdef123" not in result
    assert "token=" in result
    assert "other=ok" in result


def test_scrub_callback_rewrites_bearer_token():
    value = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.some.payload"
    result = _sanitize_value(value)
    assert "eyJhbGciOiJSUzI1NiJ9" not in result
    assert "Bearer" in result


def test_scrub_callback_rewrites_goog_signature():
    value = (
        "https://storage.googleapis.com/bucket/file?X-Goog-Signature=abc123def&X-Goog-Expires=3600"
    )
    result = _sanitize_value(value)
    assert "abc123def" not in result
    assert "X-Goog-Signature=" in result


def test_scrub_callback_rewrites_amz_signature():
    value = "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=deadbeef&X-Amz-Expires=900"
    result = _sanitize_value(value)
    assert "deadbeef" not in result
    assert "X-Amz-Signature=" in result


def test_scrub_callback_preserves_non_credential_value():
    value = "Hello world, this is a normal string."
    result = _sanitize_value(value)
    assert result == value


def test_builtin_scrub_patterns_non_empty():
    assert len(URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS) > 0
    assert any("token=" in p for p in URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS)
    assert any("bearer" in p.lower() for p in URL_SCAN_LOGFIRE_BUILTIN_SCRUB_PATTERNS)


def test_augment_logfire_installs_scrubbing_even_when_content_disabled():
    from src.url_content_scan import observability

    mock_logfire = MagicMock()
    mock_scrubbing_options = MagicMock()
    mock_logfire.ScrubbingOptions.return_value = mock_scrubbing_options

    original_state = list(observability._instrument_pydantic_ai_state)
    try:
        observability._instrument_pydantic_ai_state[0] = False
        with patch.dict("sys.modules", {"logfire": mock_logfire}):
            from src.url_content_scan.observability import augment_logfire

            augment_logfire(enable_content=False)

        mock_logfire.configure.assert_called_once()
        configure_kwargs = mock_logfire.configure.call_args.kwargs
        assert "scrubbing" in configure_kwargs
        mock_logfire.ScrubbingOptions.assert_called_once()
        scrub_call = mock_logfire.ScrubbingOptions.call_args
        assert scrub_call.kwargs.get("callback") is not None
    finally:
        observability._instrument_pydantic_ai_state[0] = original_state[0]


def test_augment_logfire_installs_scrubbing_when_content_enabled():
    from src.url_content_scan import observability

    mock_logfire = MagicMock()
    mock_scrubbing_options = MagicMock()
    mock_logfire.ScrubbingOptions.return_value = mock_scrubbing_options

    original_state = list(observability._instrument_pydantic_ai_state)
    try:
        observability._instrument_pydantic_ai_state[0] = False
        with patch.dict("sys.modules", {"logfire": mock_logfire}):
            from src.url_content_scan.observability import augment_logfire

            augment_logfire(enable_content=True)

        mock_logfire.configure.assert_called_once()
        configure_kwargs = mock_logfire.configure.call_args.kwargs
        assert "scrubbing" in configure_kwargs
    finally:
        observability._instrument_pydantic_ai_state[0] = original_state[0]
