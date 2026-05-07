from typing import Any

from fastapi import Depends, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.analyses.synthesis._weather_schemas import _normalize_weather_schema_names
from src.auth.cloud_tasks_oidc import verify_cloud_tasks_oidc
from src.monitoring import get_logger
from src.routes import _schema_anchor, analyze, analyze_pdf, frame, internal_jobs, scrape
from src.startup import lifespan

logger = get_logger(__name__)

app = FastAPI(title="vibecheck-server", version="0.1.0", lifespan=lifespan)
app.state.limiter = analyze.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
app.add_middleware(SlowAPIMiddleware)
app.include_router(frame.router)
app.include_router(analyze.router)
app.include_router(scrape.router)
app.include_router(analyze_pdf.router)
app.include_router(internal_jobs.router)
app.include_router(_schema_anchor.router)

_original_openapi = app.openapi


def _normalize_weather_openapi() -> dict[str, Any]:
    if app.openapi_schema is None:
        app.openapi_schema = _normalize_weather_schema_names(_original_openapi())
    return app.openapi_schema


app.openapi = _normalize_weather_openapi


@app.get("/metrics", dependencies=[Depends(verify_cloud_tasks_oidc)])
async def metrics() -> Response:
    """Prometheus scrape target gated behind OIDC (TASK-1473.37).

    The previous `app.mount("/metrics", make_asgi_app())` exposed job
    throughput, error counts by host, single-flight contention, and
    other operational signals to anyone on the internet whenever Cloud
    Run was configured with `--allow-unauthenticated`. We share the
    same OIDC dependency the internal worker uses so a misconfigured
    Cloud Run revision still rejects unsigned scrape attempts.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
@app.get("/health")
@app.get("/_healthz")
async def health() -> dict[str, str]:
    # Cloud Run's startup HTTP probe hits '/_healthz' per modules/gcp/cloud-run
    # — also answer '/' and '/health' for convenience.
    return {"status": "ok"}
