import asyncio
import logging
import signal
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import settings  # noqa: E402
from src.database import init_db  # noqa: E402
from src.events.nats_client import nats_client  # noqa: E402
from src.workers.audit_worker import AuditWorker  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Initializing audit worker...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"NATS URL: {settings.NATS_URL}")
    logger.info(f"Database URL: {settings.DATABASE_URL.split('@')[-1]}")

    await init_db()
    logger.info("Database initialized")

    await nats_client.connect()
    logger.info("NATS client connected")

    worker = AuditWorker()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: worker.handle_signal(s),
        )

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        raise
    finally:
        await worker.stop()
        await nats_client.disconnect()
        logger.info("Audit worker shutdown complete")


if __name__ == "__main__":
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    if settings.ENABLE_JSON_LOGGING:
        from pythonjsonlogger import jsonlogger

        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logging.basicConfig(level=log_level, handlers=[handler])
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    logger.info("Starting Open Notes Audit Worker")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
