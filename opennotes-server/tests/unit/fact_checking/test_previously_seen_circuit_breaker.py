"""Tests for the OpenAI embedding circuit breaker in previously_seen_jsonapi_router."""

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from src.circuit_breaker_core import CircuitOpenError, CircuitState
from src.fact_checking.previously_seen_jsonapi_router import (
    _build_check_response,
    _is_openai_transient_error,
    openai_embedding_breaker,
)


class TestIsOpenAITransientError:
    def test_model_http_error_429_matches(self):
        exc = ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is True

    def test_model_http_error_500_matches(self):
        exc = ModelHTTPError(status_code=500, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is True

    def test_model_http_error_503_matches(self):
        exc = ModelHTTPError(status_code=503, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is True

    def test_model_http_error_400_does_not_match(self):
        exc = ModelHTTPError(status_code=400, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is False

    def test_model_http_error_401_does_not_match(self):
        exc = ModelHTTPError(status_code=401, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is False

    def test_model_http_error_404_does_not_match(self):
        exc = ModelHTTPError(status_code=404, model_name="openai:text-embedding-3-small")
        assert _is_openai_transient_error(exc) is False

    def test_model_api_error_matches(self):
        exc = ModelAPIError(model_name="openai:text-embedding-3-small", message="quota exceeded")
        assert _is_openai_transient_error(exc) is True

    def test_value_error_does_not_match(self):
        exc = ValueError("some error")
        assert _is_openai_transient_error(exc) is False

    def test_timeout_error_does_not_match(self):
        exc = TimeoutError("timed out")
        assert _is_openai_transient_error(exc) is False

    def test_connection_error_does_not_match(self):
        exc = ConnectionError("connection refused")
        assert _is_openai_transient_error(exc) is False


class TestOpenAIEmbeddingBreakerRegistration:
    def test_breaker_registered_with_correct_name(self):
        assert openai_embedding_breaker.name == "openai_embeddings"

    def test_breaker_has_correct_failure_threshold(self):
        status = openai_embedding_breaker.get_status()
        assert status["failure_threshold"] == 3

    def test_breaker_has_correct_timeout(self):
        status = openai_embedding_breaker.get_status()
        assert status["timeout"] == 30

    def test_breaker_has_correct_backoff_rate(self):
        status = openai_embedding_breaker.get_status()
        assert status["backoff_rate"] == 2.0


class TestCircuitBreakerTripsOnQuotaErrors:
    @pytest.fixture(autouse=True)
    async def _reset_breaker(self):
        await openai_embedding_breaker.reset()
        yield
        await openai_embedding_breaker.reset()

    @pytest.mark.asyncio
    async def test_trips_after_3_model_http_429_errors(self):
        async def failing_call():
            raise ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")

        for _ in range(3):
            with pytest.raises(ModelHTTPError):
                await openai_embedding_breaker.call(failing_call)

        assert openai_embedding_breaker.state == CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await openai_embedding_breaker.call(failing_call)

    @pytest.mark.asyncio
    async def test_trips_after_3_model_api_errors(self):
        async def failing_call():
            raise ModelAPIError(
                model_name="openai:text-embedding-3-small", message="quota exceeded"
            )

        for _ in range(3):
            with pytest.raises(ModelAPIError):
                await openai_embedding_breaker.call(failing_call)

        assert openai_embedding_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_does_not_trip_on_model_http_400(self):
        async def failing_call():
            raise ModelHTTPError(status_code=400, model_name="openai:text-embedding-3-small")

        for _ in range(5):
            with pytest.raises(ModelHTTPError):
                await openai_embedding_breaker.call(failing_call)

        assert openai_embedding_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_does_not_trip_on_value_error(self):
        async def failing_call():
            raise ValueError("bad input")

        for _ in range(5):
            with pytest.raises(ValueError, match="bad input"):
                await openai_embedding_breaker.call(failing_call)

        assert openai_embedding_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_mixed_errors_only_quota_errors_count(self):
        async def quota_error():
            raise ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")

        async def client_error():
            raise ModelHTTPError(status_code=400, model_name="openai:text-embedding-3-small")

        with pytest.raises(ModelHTTPError):
            await openai_embedding_breaker.call(quota_error)
        with pytest.raises(ModelHTTPError):
            await openai_embedding_breaker.call(client_error)
        with pytest.raises(ModelHTTPError):
            await openai_embedding_breaker.call(quota_error)

        assert openai_embedding_breaker.state == CircuitState.CLOSED
        assert openai_embedding_breaker.failures == 2

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        async def quota_error():
            raise ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")

        async def success():
            return [0.1] * 1536

        with pytest.raises(ModelHTTPError):
            await openai_embedding_breaker.call(quota_error)
        with pytest.raises(ModelHTTPError):
            await openai_embedding_breaker.call(quota_error)

        assert openai_embedding_breaker.failures == 2

        result = await openai_embedding_breaker.call(success)
        assert result == [0.1] * 1536
        assert openai_embedding_breaker.failures == 0
        assert openai_embedding_breaker.state == CircuitState.CLOSED


class TestBuildCheckResponse:
    def test_empty_matches_fail_open(self):
        response = _build_check_response(
            matches=[],
            should_auto_publish=False,
            should_auto_request=False,
            autopublish_threshold=0.95,
            autorequest_threshold=0.85,
        )
        assert response.status_code == 200

        import json

        body = json.loads(response.body.decode())
        attrs = body["data"]["attributes"]
        assert attrs["should_auto_publish"] is False
        assert attrs["should_auto_request"] is False
        assert attrs["matches"] == []
        assert attrs["top_match"] is None
        assert attrs["autopublish_threshold"] == 0.95
        assert attrs["autorequest_threshold"] == 0.85

    def test_response_has_jsonapi_version(self):
        response = _build_check_response(
            matches=[],
            should_auto_publish=False,
            should_auto_request=False,
            autopublish_threshold=0.95,
            autorequest_threshold=0.85,
        )

        import json

        body = json.loads(response.body.decode())
        assert body["jsonapi"] == {"version": "1.1"}

    def test_response_has_correct_resource_type(self):
        response = _build_check_response(
            matches=[],
            should_auto_publish=False,
            should_auto_request=False,
            autopublish_threshold=0.95,
            autorequest_threshold=0.85,
        )

        import json

        body = json.loads(response.body.decode())
        assert body["data"]["type"] == "previously-seen-check-result"
        assert "id" in body["data"]


class TestCircuitBreakerFailOpenIntegration:
    @pytest.fixture(autouse=True)
    async def _reset_breaker(self):
        await openai_embedding_breaker.reset()
        yield
        await openai_embedding_breaker.reset()

    @pytest.mark.asyncio
    async def test_circuit_open_produces_fail_open_response(self):
        async def quota_error():
            raise ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")

        for _ in range(3):
            with pytest.raises(ModelHTTPError):
                await openai_embedding_breaker.call(quota_error)

        assert openai_embedding_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await openai_embedding_breaker.call(quota_error)

        response = _build_check_response(
            matches=[],
            should_auto_publish=False,
            should_auto_request=False,
            autopublish_threshold=0.95,
            autorequest_threshold=0.85,
        )

        import json

        body = json.loads(response.body.decode())
        assert body["data"]["attributes"]["should_auto_publish"] is False
        assert body["data"]["attributes"]["should_auto_request"] is False
        assert body["data"]["attributes"]["matches"] == []


class TestCriticalLogOnCircuitTrip:
    @pytest.fixture(autouse=True)
    async def _reset_breaker(self):
        await openai_embedding_breaker.reset()
        yield
        await openai_embedding_breaker.reset()

    @pytest.mark.asyncio
    async def test_critical_log_emitted_when_circuit_open(self, caplog):
        import logging

        async def quota_error():
            raise ModelHTTPError(status_code=429, model_name="openai:text-embedding-3-small")

        for _ in range(3):
            with pytest.raises(ModelHTTPError):
                await openai_embedding_breaker.call(quota_error)

        assert openai_embedding_breaker.state == CircuitState.OPEN

        from src.fact_checking.previously_seen_jsonapi_router import (
            _handle_circuit_open_fail_open,
        )

        with caplog.at_level(logging.CRITICAL):
            response = _handle_circuit_open_fail_open(
                platform_community_server_id="guild-123",
                channel_id="channel-456",
                autopublish_threshold=0.95,
                autorequest_threshold=0.85,
            )

        assert any(
            record.levelno == logging.CRITICAL and "circuit breaker OPEN" in record.message
            for record in caplog.records
        )
        assert response.status_code == 200
