import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.middleware.startup_gate import StartupGateMiddleware


def _make_app(*, startup_complete: bool = False, startup_failed: bool = False) -> FastAPI:
    app = FastAPI()
    app.add_middleware(StartupGateMiddleware)
    app.state.startup_complete = startup_complete
    app.state.startup_failed = startup_failed

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/health/simple")
    async def health_simple():
        return {"status": "ok"}

    @app.get("/api/notes")
    async def notes():
        return {"notes": []}

    return app


@pytest.mark.unit
class TestStartupGateMiddleware:
    def test_non_health_returns_503_when_not_ready(self) -> None:
        app = _make_app(startup_complete=False)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/notes")

        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "starting"
        assert body["message"] == "Server initializing"

    def test_health_returns_503_when_not_ready(self) -> None:
        app = _make_app(startup_complete=False)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

        assert response.status_code == 503
        assert response.json()["error"] == "starting"

    def test_health_simple_passes_through_when_not_ready(self) -> None:
        app = _make_app(startup_complete=False)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health/simple")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_non_health_passes_through_when_ready(self) -> None:
        app = _make_app(startup_complete=True)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/notes")

        assert response.status_code == 200
        assert response.json() == {"notes": []}

    def test_any_route_returns_503_when_startup_failed(self) -> None:
        app = _make_app(startup_failed=True)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/notes")
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "startup_failed"
        assert body["message"] == "Server initialization failed"

    def test_health_returns_503_when_startup_failed(self) -> None:
        app = _make_app(startup_failed=True)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "startup_failed"
        assert body["message"] == "Server initialization failed"

    def test_defaults_to_not_ready_without_state(self) -> None:
        app = FastAPI()
        app.add_middleware(StartupGateMiddleware)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/test")

        assert response.status_code == 503
        assert response.json()["error"] == "starting"

    def test_health_returns_503_without_state(self) -> None:
        app = FastAPI()
        app.add_middleware(StartupGateMiddleware)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

        assert response.status_code == 503
        assert response.json()["error"] == "starting"
