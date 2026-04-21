from fastapi import FastAPI
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.monitoring import get_logger
from src.routes import frame

logger = get_logger(__name__)

app = FastAPI(title="vibecheck-server", version="0.1.0")
app.state.limiter = Limiter(key_func=get_remote_address)
app.include_router(frame.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
