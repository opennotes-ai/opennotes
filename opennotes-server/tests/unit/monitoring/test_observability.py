from unittest.mock import MagicMock, patch

GCP_DETECTOR_PATH = "src.monitoring.gcp_resource_detector.is_cloud_run_environment"
LOGFIRE_CONFIGURE_PATH = "logfire.configure"
LOGFIRE_INSTRUMENT_ANTHROPIC_PATH = "logfire.instrument_anthropic"
LOGFIRE_INSTRUMENT_OPENAI_PATH = "logfire.instrument_openai"


class TestObservabilityGcpExporters:
    @patch(GCP_DETECTOR_PATH, return_value=True)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    @patch("opentelemetry.sdk.trace.export.BatchSpanProcessor")
    def test_cloud_trace_in_additional_processors_on_gcp(
        self, mock_bsp, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        mock_exporter_cls = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "test", "GOOGLE_CLOUD_PROJECT": "test-project"},
                clear=False,
            ),
            patch(
                "src.monitoring.cloud_trace_logging_exporter.CloudTraceLoggingSpanExporter",
                mock_exporter_cls,
            ),
        ):
            result = obs_mod.setup_observability(
                service_name="test-service",
                service_version="0.0.1",
                environment="test",
            )

        assert result is True
        mock_configure.assert_called_once()
        call_kwargs = mock_configure.call_args[1]
        processors = call_kwargs["additional_span_processors"]
        assert len(processors) == 3

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_no_cloud_trace_when_not_on_gcp(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        result = obs_mod.setup_observability(
            service_name="test-service",
            service_version="0.0.1",
            environment="test",
        )

        assert result is True
        call_kwargs = mock_configure.call_args[1]
        processors = call_kwargs["additional_span_processors"]
        assert len(processors) == 2


class TestObservabilityLLMInstrumentation:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_instruments_anthropic_and_openai(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(service_name="test", environment="test")

        mock_anthropic.assert_called_once()
        mock_openai.assert_called_once()


class TestObservabilityTokenHandling:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_send_to_logfire_if_token_present_when_no_token(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(service_name="test", environment="test")

        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["send_to_logfire"] == "if-token-present"

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_send_to_logfire_true_when_token_provided(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(
            service_name="test", environment="test", logfire_token="test-token"
        )

        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["send_to_logfire"] is True
        assert call_kwargs["token"] == "test-token"


class TestObservabilityIdempotent:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_double_call_is_noop(self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(service_name="test", environment="test")
        obs_mod.setup_observability(service_name="test", environment="test")

        mock_configure.assert_called_once()


class TestObservabilityImportError:
    def test_graceful_fallback_when_logfire_not_installed(self):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        with patch.dict("sys.modules", {"logfire": None}):
            result = obs_mod.setup_observability(service_name="test", environment="test")

        assert result is False


class TestObservabilityDisabled:
    def test_disabled_via_env(self):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        with patch.dict("os.environ", {"OTEL_SDK_DISABLED": "true"}, clear=False):
            result = obs_mod.setup_observability(service_name="test", environment="test")

        assert result is False


class TestObservabilityConfigureParams:
    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_passes_service_metadata_to_logfire(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(
            service_name="my-service",
            service_version="1.2.3",
            environment="staging",
        )

        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["service_name"] == "my-service"
        assert call_kwargs["service_version"] == "1.2.3"
        assert call_kwargs["environment"] == "staging"

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_tail_sampling_with_custom_module_sampler(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(
            service_name="test",
            environment="test",
            sample_rate=0.3,
            tail_level_threshold="warning",
            tail_duration_threshold=10.0,
        )

        call_kwargs = mock_configure.call_args[1]
        sampling = call_kwargs["sampling"]
        assert sampling.head == 1.0
        assert sampling.tail is not None
        assert callable(sampling.tail)

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_tail_sampler_caps_dbos_worker_datastore_rate(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(
            service_name="opennotes-dbos-worker",
            environment="test",
            sample_rate=0.3,
            dbos_datastore_logfire_sample_rate=0.5,
        )

        sampling = mock_configure.call_args[1]["sampling"]
        span = MagicMock()
        span.name = "redis query"
        span.instrumentation_scope.name = "opentelemetry.instrumentation.redis"
        span.attributes = {"db.system": "redis"}
        info = MagicMock()
        info.level = "info"
        info.duration = 0.1
        info.span = span

        assert sampling.tail(info) == 0.01

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_scrubbing_disabled_when_trace_content_true(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(service_name="test", environment="test", trace_content=True)

        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["scrubbing"] is False

    @patch(GCP_DETECTOR_PATH, return_value=False)
    @patch(LOGFIRE_CONFIGURE_PATH)
    @patch(LOGFIRE_INSTRUMENT_ANTHROPIC_PATH)
    @patch(LOGFIRE_INSTRUMENT_OPENAI_PATH)
    def test_scrubbing_default_when_trace_content_false(
        self, mock_openai, mock_anthropic, mock_configure, mock_is_gcp
    ):
        import src.monitoring.observability as obs_mod

        obs_mod._observability_initialized = False

        obs_mod.setup_observability(service_name="test", environment="test", trace_content=False)

        call_kwargs = mock_configure.call_args[1]
        assert call_kwargs["scrubbing"] is None
