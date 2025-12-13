import asyncio
import logging
from typing import Protocol

import nats
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg
from nats.errors import Error as NATSError
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, PubAck, RetentionPolicy, StorageType, StreamConfig

from src.circuit_breaker import circuit_breaker_registry
from src.config import settings

logger = logging.getLogger(__name__)


class MessageCallback(Protocol):
    async def __call__(self, msg: Msg) -> None: ...


class Subscription(Protocol):
    async def unsubscribe(self) -> None: ...


class NATSClientManager:
    def __init__(self) -> None:
        self.nc: NATSClient | None = None
        self.js: JetStreamContext | None = None
        self.circuit_breaker = circuit_breaker_registry.get_breaker(
            name="nats",
            expected_exception=NATSError,
        )

    async def connect(
        self,
        timeout: float = 10.0,
        max_startup_retries: int = 5,
        retry_backoff_base: float = 2.0,
    ) -> None:
        """Connect to NATS with startup retry logic.

        Args:
            timeout: Timeout for each connection attempt
            max_startup_retries: Number of times to retry initial connection
            retry_backoff_base: Base for exponential backoff (wait = base^attempt seconds)
        """
        url = settings.NATS_URL
        has_auth = settings.NATS_USERNAME and settings.NATS_PASSWORD
        logger.info(f"Connecting to NATS at {url} (auth: {has_auth})")

        connect_kwargs: dict[str, object] = {
            "servers": [url],
            "max_reconnect_attempts": settings.NATS_MAX_RECONNECT_ATTEMPTS,
            "reconnect_time_wait": settings.NATS_RECONNECT_WAIT,
        }

        if has_auth:
            connect_kwargs["user"] = settings.NATS_USERNAME
            connect_kwargs["password"] = settings.NATS_PASSWORD

        last_error: BaseException | None = None
        for attempt in range(max_startup_retries):
            try:
                self.nc = await asyncio.wait_for(
                    nats.connect(**connect_kwargs),  # type: ignore[arg-type]
                    timeout=timeout,
                )

                # Configure JetStream with increased timeout for API operations
                # Default 5s timeout is too short during concurrent startup operations
                # which can cause subscribe/consumer_info timeouts
                self.js = self.nc.jetstream(timeout=30.0)

                await self._ensure_stream()

                logger.info(f"Connected to NATS at {url}")
                return
            except (TimeoutError, asyncio.CancelledError, Exception) as e:
                last_error = e
                if attempt < max_startup_retries - 1:
                    wait_time = retry_backoff_base**attempt
                    logger.warning(
                        f"NATS connection attempt {attempt + 1}/{max_startup_retries} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"NATS connection failed after {max_startup_retries} attempts. Last error: {e}"
                    )

        # All retries exhausted
        raise ConnectionError(
            f"Failed to connect to NATS at {url} after {max_startup_retries} attempts"
        ) from last_error

    async def disconnect(self) -> None:
        if self.nc:
            try:
                await self.nc.drain()
            except Exception as e:
                logger.error(f"Error draining NATS connection: {e}")
            finally:
                try:
                    await self.nc.close()
                except Exception as e:
                    logger.error(f"Error closing NATS connection: {e}")
                finally:
                    self.nc = None
                    self.js = None
                    logger.info("Disconnected from NATS")

    async def _ensure_stream(self) -> None:
        if not self.js:
            raise RuntimeError("JetStream context not initialized")

        max_retries = 5
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                await self.js.stream_info(settings.NATS_STREAM_NAME)
                logger.info(f"Stream '{settings.NATS_STREAM_NAME}' already exists")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.warning(
                        f"stream_info failed after {max_retries} attempts, "
                        f"attempting to create stream: {e}"
                    )
                    break
                logger.debug(
                    f"stream_info attempt {attempt + 1}/{max_retries} failed, "
                    f"retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 5.0)

        try:
            logger.info(f"Creating stream '{settings.NATS_STREAM_NAME}'")
            await self.js.add_stream(
                StreamConfig(
                    name=settings.NATS_STREAM_NAME,
                    subjects=[f"{settings.NATS_STREAM_NAME}.>"],
                    retention=RetentionPolicy.WORK_QUEUE,
                    storage=StorageType.FILE,
                    max_age=settings.NATS_STREAM_MAX_AGE_SECONDS,
                    max_msgs=settings.NATS_STREAM_MAX_MESSAGES,
                    max_bytes=settings.NATS_STREAM_MAX_BYTES,
                    duplicate_window=settings.NATS_STREAM_DUPLICATE_WINDOW_SECONDS,
                )
            )
        except Exception as e:
            logger.error(f"Failed to create stream '{settings.NATS_STREAM_NAME}': {e}")
            raise

    async def publish(
        self,
        subject: str,
        data: bytes,
        headers: dict[str, str] | None = None,
    ) -> PubAck:
        if not self.nc or not self.js:
            raise RuntimeError("NATS client not connected")

        try:
            return await self.circuit_breaker.call(
                self.js.publish,
                subject,
                data,
                headers=headers,
            )
        except Exception as e:
            logger.error(f"Failed to publish to subject '{subject}': {e}")
            raise

    async def subscribe(
        self,
        subject: str,
        queue: str,
        callback: MessageCallback,
        durable: str | None = None,
    ) -> Subscription:
        if not self.nc:
            raise RuntimeError("NATS client not connected")

        if not self.js:
            raise RuntimeError("JetStream context not initialized")

        config_params: dict[str, int | str] = {
            "max_deliver": settings.NATS_MAX_DELIVER_ATTEMPTS,
            "ack_wait": settings.NATS_ACK_WAIT_SECONDS,
        }
        if durable is not None:
            config_params["durable_name"] = durable

        consumer_config = ConsumerConfig(**config_params)  # type: ignore[arg-type]

        try:
            return await asyncio.wait_for(
                self.js.subscribe(
                    subject,
                    queue=queue,
                    cb=callback,
                    config=consumer_config,
                ),
                timeout=10.0,
            )
        except Exception as e:
            logger.error(f"Failed to subscribe to subject '{subject}': {e}")
            raise

    async def is_connected(self) -> bool:
        if not self.nc:
            return False

        return self.nc.is_connected

    async def ping(self) -> bool:
        if not self.nc:
            return False

        try:
            await self.circuit_breaker.call(self.nc.flush, timeout=2)
            return True
        except Exception as e:
            logger.debug(f"NATS ping failed: {e}")
            return False


nats_client = NATSClientManager()
