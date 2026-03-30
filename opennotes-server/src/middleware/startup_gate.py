from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class StartupGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        startup_failed = getattr(request.app.state, "startup_failed", False)
        if startup_failed:
            return JSONResponse(
                status_code=503,
                content={"error": "startup_failed", "message": "Server initialization failed"},
            )

        startup_complete = getattr(request.app.state, "startup_complete", False)
        if not startup_complete:
            if request.url.path.startswith("/health") or request.url.path == "/version":
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={"error": "starting", "message": "Server initializing"},
            )

        return await call_next(request)
