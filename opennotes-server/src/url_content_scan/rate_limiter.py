from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from src.users.models import APIKey

logger = logging.getLogger(__name__)

DEFAULT_API_KEY_LIMIT = 600
DEFAULT_API_KEY_WINDOW_SECONDS = 60 * 60
DEFAULT_IP_URL_LIMIT = 30
DEFAULT_IP_URL_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitStatus:
    allowed: bool
    bucket: str
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_at_epoch: int
    window_seconds: int
    failed_open: bool = False


class UrlScanRateLimiter:
    def __init__(
        self,
        redis_client: Any | None,
        *,
        api_key_limit: int = DEFAULT_API_KEY_LIMIT,
        api_key_window_seconds: int = DEFAULT_API_KEY_WINDOW_SECONDS,
        ip_url_limit: int = DEFAULT_IP_URL_LIMIT,
        ip_url_window_seconds: int = DEFAULT_IP_URL_WINDOW_SECONDS,
    ) -> None:
        self.redis_client = redis_client
        self.api_key_limit = api_key_limit
        self.api_key_window_seconds = api_key_window_seconds
        self.ip_url_limit = ip_url_limit
        self.ip_url_window_seconds = ip_url_window_seconds

    async def check_api_key_limit(self, api_key: APIKey) -> RateLimitStatus:
        api_key_identifier = self._api_key_identifier(api_key)
        return await self._check_fixed_window(
            bucket=f"url_scan:api_key:{api_key_identifier}",
            limit=self.api_key_limit,
            window_seconds=self.api_key_window_seconds,
        )

    async def check_ip_url_limit(self, ip_address: str, normalized_url: str) -> RateLimitStatus:
        return await self._check_fixed_window(
            bucket=f"url_scan:ip_url:{ip_address}:{normalized_url}",
            limit=self.ip_url_limit,
            window_seconds=self.ip_url_window_seconds,
        )

    async def _check_fixed_window(
        self,
        *,
        bucket: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitStatus:
        now = int(time.time())
        window_id = now // window_seconds
        redis_key = f"{bucket}:{window_id}"
        reset_at_epoch = (window_id + 1) * window_seconds

        if self.redis_client is None:
            logger.error(
                "URL scan rate limiting is fail-open because Redis is unavailable for bucket %s",
                bucket,
            )
            return self._fail_open_status(
                bucket=bucket,
                limit=limit,
                window_seconds=window_seconds,
                reset_at_epoch=reset_at_epoch,
            )

        try:
            current_count = await self.redis_client.incr(redis_key)
            if current_count == 1:
                await self.redis_client.expire(redis_key, window_seconds)

            ttl = await self.redis_client.ttl(redis_key)
            if ttl < 0:
                await self.redis_client.expire(redis_key, window_seconds)
                ttl = window_seconds

            allowed = current_count <= limit
            remaining = max(0, limit - current_count)

            return RateLimitStatus(
                allowed=allowed,
                bucket=bucket,
                limit=limit,
                remaining=remaining,
                retry_after_seconds=max(0, ttl if not allowed else 0),
                reset_at_epoch=reset_at_epoch,
                window_seconds=window_seconds,
                failed_open=False,
            )
        except Exception:
            logger.exception(
                "URL scan rate limiting is fail-open because Redis errored for bucket %s",
                bucket,
            )
            return self._fail_open_status(
                bucket=bucket,
                limit=limit,
                window_seconds=window_seconds,
                reset_at_epoch=reset_at_epoch,
            )

    def _api_key_identifier(self, api_key: APIKey) -> str:
        if getattr(api_key, "id", None) is not None:
            return str(api_key.id)
        if getattr(api_key, "key_prefix", None):
            return str(api_key.key_prefix)
        if getattr(api_key, "name", None):
            return str(api_key.name)
        raise ValueError("URL scan rate limiting requires a persisted APIKey identifier")

    def _fail_open_status(
        self,
        *,
        bucket: str,
        limit: int,
        window_seconds: int,
        reset_at_epoch: int,
    ) -> RateLimitStatus:
        return RateLimitStatus(
            allowed=True,
            bucket=bucket,
            limit=limit,
            remaining=limit,
            retry_after_seconds=0,
            reset_at_epoch=reset_at_epoch,
            window_seconds=window_seconds,
            failed_open=True,
        )
