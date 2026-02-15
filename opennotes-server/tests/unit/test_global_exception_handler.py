from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient


def _build_app(*, debug: bool = False) -> FastAPI:
    app = FastAPI()

    @app.get("/explode")
    async def explode():
        raise RuntimeError("kaboom")

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        import logging

        try:
            from src.monitoring import record_span_error

            record_span_error(exc)

            http_context = {
                "method": request.method,
                "url": str(request.url),
                "userAgent": request.headers.get("user-agent", ""),
                "remoteIp": request.client.host if request.client else None,
                "referrer": request.headers.get("referer", ""),
            }

            from src.monitoring import get_logger

            logger = get_logger(__name__)
            logger.exception(
                f"Unhandled exception: {exc}",
                extra={"httpRequest": http_context},
            )
        except Exception:
            logging.getLogger(__name__).error(
                "Unhandled exception (error handler fallback): %s",
                exc,
                exc_info=True,
            )

        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred",
                "details": str(exc) if debug else None,
            },
        )

    return app


@pytest.mark.unit
class TestGlobalExceptionHandler:
    def test_returns_500_with_error_body(self):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/explode")

        assert response.status_code == 500
        body = response.json()
        assert body["error"] == "internal_server_error"
        assert body["message"] == "An unexpected error occurred"
        assert body["details"] is None

    def test_includes_details_in_debug_mode(self):
        client = TestClient(_build_app(debug=True), raise_server_exceptions=False)
        response = client.get("/explode")

        assert response.status_code == 500
        body = response.json()
        assert body["details"] == "kaboom"

    @patch("src.monitoring.record_span_error")
    def test_calls_record_span_error(self, mock_record):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        client.get("/explode")

        mock_record.assert_called_once()
        exc_arg = mock_record.call_args[0][0]
        assert isinstance(exc_arg, RuntimeError)
        assert str(exc_arg) == "kaboom"

    def test_log_contains_http_request_context(self, caplog):
        client = TestClient(_build_app(), raise_server_exceptions=False)

        with caplog.at_level("ERROR"):
            client.get("/explode")

        error_records = [r for r in caplog.records if "Unhandled exception" in r.getMessage()]
        assert len(error_records) >= 1

        record = error_records[0]
        http_request = getattr(record, "httpRequest", None)
        assert http_request is not None
        assert http_request["method"] == "GET"
        assert "/explode" in http_request["url"]

    def test_fallback_on_handler_failure(self, caplog):
        app = FastAPI()

        @app.get("/explode")
        async def explode():
            raise RuntimeError("kaboom")

        @app.exception_handler(Exception)
        async def handler_with_broken_enrichment(request, exc):
            import logging

            try:
                raise TypeError("enrichment broken")
            except Exception:
                logging.getLogger(__name__).error(
                    "Unhandled exception (error handler fallback): %s",
                    exc,
                    exc_info=True,
                )

            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred",
                    "details": None,
                },
            )

        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level("ERROR"):
            response = client.get("/explode")

        assert response.status_code == 500
        fallback_records = [r for r in caplog.records if "error handler fallback" in r.getMessage()]
        assert len(fallback_records) >= 1
