from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.monitoring import get_logger
from src.routes import analyze, frame
from src.startup import lifespan

logger = get_logger(__name__)

app = FastAPI(title="vibecheck-server", version="0.1.0", lifespan=lifespan)
app.state.limiter = analyze.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
app.add_middleware(SlowAPIMiddleware)
app.include_router(frame.router)
app.include_router(analyze.router)


@app.get("/")
@app.get("/health")
@app.get("/_healthz")
async def health() -> dict[str, str]:
    # Cloud Run's startup HTTP probe hits '/_healthz' per modules/gcp/cloud-run
    # — also answer '/' and '/health' for convenience.
    return {"status": "ok"}
