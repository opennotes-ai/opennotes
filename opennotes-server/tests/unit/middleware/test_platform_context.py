from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.auth.platform_claims import create_platform_claims_token


@pytest.mark.unit
class TestPlatformContextMiddleware:
    def test_platform_claims_set_span_attributes(self) -> None:
        from src.middleware.platform_context import PlatformContextMiddleware

        app = FastAPI()
        app.add_middleware(PlatformContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        token = create_platform_claims_token(
            platform="discord",
            scope="*",
            sub="123456789",
            community_id="987654321",
            can_administer_community=True,
            username="testuser",
        )

        with (
            patch(
                "src.middleware.platform_context.trace.get_current_span",
                return_value=mock_span,
            ),
            patch("src.middleware.platform_context.baggage.set_baggage") as mock_baggage,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={
                    "x-platform-type": "discord",
                    "x-platform-claims": token,
                },
            )

        assert response.status_code == 200
        assert captured_attributes.get("platform.type") == "discord"
        assert captured_attributes.get("platform.user_id") == "123456789"
        assert captured_attributes.get("platform.scope") == "*"
        assert captured_attributes.get("platform.community_id") == "987654321"

        baggage_calls = [call[0] for call in mock_baggage.call_args_list]
        assert any(call[0] == "platform.type" and call[1] == "discord" for call in baggage_calls)
        assert any(
            call[0] == "platform.user_id" and call[1] == "123456789" for call in baggage_calls
        )

    def test_platform_type_only_sets_type_attribute(self) -> None:
        from src.middleware.platform_context import PlatformContextMiddleware

        app = FastAPI()
        app.add_middleware(PlatformContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with (
            patch(
                "src.middleware.platform_context.trace.get_current_span",
                return_value=mock_span,
            ),
            patch("src.middleware.platform_context.baggage.set_baggage") as mock_baggage,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={"x-platform-type": "discourse"},
            )

        assert response.status_code == 200
        assert captured_attributes.get("platform.type") == "discourse"
        assert "platform.user_id" not in captured_attributes

        baggage_calls = [call[0] for call in mock_baggage.call_args_list]
        assert any(call[0] == "platform.type" and call[1] == "discourse" for call in baggage_calls)

    def test_no_platform_headers_sets_nothing(self) -> None:
        from src.middleware.platform_context import PlatformContextMiddleware

        app = FastAPI()
        app.add_middleware(PlatformContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with patch(
            "src.middleware.platform_context.trace.get_current_span",
            return_value=mock_span,
        ):
            client = TestClient(app)
            response = client.get("/test")

        assert response.status_code == 200
        assert "platform.type" not in captured_attributes
        assert "platform.user_id" not in captured_attributes

    def test_invalid_claims_token_only_sets_type(self) -> None:
        from src.middleware.platform_context import PlatformContextMiddleware

        app = FastAPI()
        app.add_middleware(PlatformContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with patch(
            "src.middleware.platform_context.trace.get_current_span",
            return_value=mock_span,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={
                    "x-platform-type": "discord",
                    "x-platform-claims": "invalid.jwt.token",
                },
            )

        assert response.status_code == 200
        assert captured_attributes.get("platform.type") == "discord"
        assert "platform.user_id" not in captured_attributes

    def test_request_id_propagated(self) -> None:
        from src.middleware.platform_context import PlatformContextMiddleware

        app = FastAPI()
        app.add_middleware(PlatformContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with (
            patch(
                "src.middleware.platform_context.trace.get_current_span",
                return_value=mock_span,
            ),
            patch("src.middleware.platform_context.baggage.set_baggage") as mock_baggage,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={"x-request-id": "req-abc-123"},
            )

        assert response.status_code == 200
        assert captured_attributes.get("http.request_id") == "req-abc-123"

        baggage_calls = [call[0] for call in mock_baggage.call_args_list]
        assert any(call[0] == "request_id" and call[1] == "req-abc-123" for call in baggage_calls)
