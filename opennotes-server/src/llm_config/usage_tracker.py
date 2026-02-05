"""
Usage tracking for LLM API calls.

Provides rate limiting and budget tracking per community server,
with automatic counter resets for daily and monthly limits.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm_config.cost_calculator import LLMCostCalculator
from src.llm_config.models import CommunityServerLLMConfig, LLMUsageLog


class LLMUsageLimitExceeded(Exception):  # noqa: N818
    """Raised when LLM usage limits are exceeded."""


class LLMUsageTracker:
    """
    Tracks LLM usage and enforces rate limits.

    Manages per-community-server usage counters and limits, with automatic
    resets for daily and monthly periods.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize usage tracker.

        Args:
            db: Database session
        """
        self.db = db

    async def check_limits(  # noqa: PLR0911, PLR0912
        self,
        community_server_id: UUID,
        provider: str,
        estimated_tokens: int = 0,
        model: str | None = None,
        estimated_cost: Decimal | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if a request would exceed configured limits.

        Validates multiple limit types (requests, tokens, spending) with cost calculation.
        Automatically resets counters if the daily or monthly period has passed.

        Args:
            community_server_id: Community server UUID
            provider: Provider name
            estimated_tokens: Estimated tokens for the request (optional)
            model: Model identifier (required if checking cost limits)
            estimated_cost: Pre-calculated cost estimate (optional, calculated if not provided)

        Returns:
            Tuple of (allowed, reason) where:
            - allowed: True if request is within limits
            - reason: Error message if not allowed, None otherwise
        """
        config = await self._get_config(community_server_id, provider)
        if not config or not config.enabled:
            # Check if global fallback OpenAI API key exists
            if settings.OPENAI_API_KEY:
                return True, None
            return False, "Provider not configured or disabled"

        await self._reset_counters_if_needed(config)

        if (
            config.daily_request_limit
            and config.current_daily_requests >= config.daily_request_limit
        ):
            return False, f"Daily request limit reached ({config.daily_request_limit})"

        if (
            config.monthly_request_limit
            and config.current_monthly_requests >= config.monthly_request_limit
        ):
            return False, f"Monthly request limit reached ({config.monthly_request_limit})"

        if estimated_tokens > 0:
            if config.daily_token_limit and (
                config.current_daily_tokens + estimated_tokens > config.daily_token_limit
            ):
                return False, "Daily token limit would be exceeded"

            if config.monthly_token_limit and (
                config.current_monthly_tokens + estimated_tokens > config.monthly_token_limit
            ):
                return False, "Monthly token limit would be exceeded"

        # Check spending limits
        if config.daily_spend_limit or config.monthly_spend_limit:
            if estimated_cost is None and estimated_tokens > 0 and model:
                try:
                    estimated_cost = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                        provider, model, estimated_tokens
                    )
                except ValueError:
                    # Unknown model - skip cost check
                    pass

            if estimated_cost is not None:
                current_daily_spend = Decimal(str(config.current_daily_spend))
                current_monthly_spend = Decimal(str(config.current_monthly_spend))

                if config.daily_spend_limit:
                    daily_limit = Decimal(str(config.daily_spend_limit))
                    if current_daily_spend + estimated_cost > daily_limit:
                        return False, f"Daily spending limit would be exceeded (${daily_limit})"

                if config.monthly_spend_limit:
                    monthly_limit = Decimal(str(config.monthly_spend_limit))
                    if current_monthly_spend + estimated_cost > monthly_limit:
                        return False, f"Monthly spending limit would be exceeded (${monthly_limit})"

        return True, None

    async def check_and_reserve_limits(  # noqa: PLR0911, PLR0912
        self,
        community_server_id: UUID,
        provider: str,
        estimated_tokens: int,
        model: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Atomically check limits and reserve tokens if allowed.

        This prevents TOCTOU race conditions by using SELECT FOR UPDATE to lock
        the configuration row, checking limits, and updating counters atomically.
        Reserved tokens count toward usage limits immediately.

        Args:
            community_server_id: Community server UUID
            provider: Provider name
            estimated_tokens: Estimated tokens to reserve
            model: Model identifier (optional, for cost estimation)

        Returns:
            Tuple of (allowed, reason) where:
            - allowed: True if request is within limits and tokens reserved
            - reason: Error message if not allowed, None otherwise
        """
        max_retries = 3
        for _attempt in range(max_retries):
            try:
                if self.db.in_transaction():
                    transaction = self.db.begin_nested()
                else:
                    transaction = self.db.begin()

                async with transaction:
                    stmt = (
                        select(CommunityServerLLMConfig)
                        .where(
                            CommunityServerLLMConfig.community_server_id == community_server_id,
                            CommunityServerLLMConfig.provider == provider,
                        )
                        .with_for_update()
                    )
                    result = await self.db.execute(stmt)
                    config = result.scalar_one_or_none()

                    if not config or not config.enabled:
                        if settings.OPENAI_API_KEY:
                            return True, None
                        return False, "Provider not configured or disabled"

                    await self._reset_counters_if_needed_in_transaction(config)
                    await self.db.refresh(config)

                    estimated_cost: Decimal | None = None
                    if (config.daily_spend_limit or config.monthly_spend_limit) and model:
                        try:
                            estimated_cost = (
                                await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                                    provider, model, estimated_tokens
                                )
                            )
                        except ValueError:
                            pass

                    new_daily_requests = config.current_daily_requests + 1
                    new_monthly_requests = config.current_monthly_requests + 1
                    new_daily_tokens = config.current_daily_tokens + estimated_tokens
                    new_monthly_tokens = config.current_monthly_tokens + estimated_tokens

                    if (
                        config.daily_request_limit
                        and new_daily_requests > config.daily_request_limit
                    ):
                        return False, f"Daily request limit reached ({config.daily_request_limit})"

                    if (
                        config.monthly_request_limit
                        and new_monthly_requests > config.monthly_request_limit
                    ):
                        return (
                            False,
                            f"Monthly request limit reached ({config.monthly_request_limit})",
                        )

                    if config.daily_token_limit and new_daily_tokens > config.daily_token_limit:
                        return False, "Daily token limit would be exceeded"

                    if (
                        config.monthly_token_limit
                        and new_monthly_tokens > config.monthly_token_limit
                    ):
                        return False, "Monthly token limit would be exceeded"

                    new_daily_spend = Decimal(str(config.current_daily_spend))
                    new_monthly_spend = Decimal(str(config.current_monthly_spend))

                    if estimated_cost is not None:
                        new_daily_spend += estimated_cost
                        new_monthly_spend += estimated_cost

                        if config.daily_spend_limit:
                            daily_limit = Decimal(str(config.daily_spend_limit))
                            if new_daily_spend > daily_limit:
                                return (
                                    False,
                                    f"Daily spending limit would be exceeded (${daily_limit})",
                                )

                        if config.monthly_spend_limit:
                            monthly_limit = Decimal(str(config.monthly_spend_limit))
                            if new_monthly_spend > monthly_limit:
                                return (
                                    False,
                                    f"Monthly spending limit would be exceeded (${monthly_limit})",
                                )

                    update_stmt = (
                        update(CommunityServerLLMConfig)
                        .where(
                            CommunityServerLLMConfig.id == config.id,
                            CommunityServerLLMConfig.version == config.version,
                        )
                        .values(
                            current_daily_requests=new_daily_requests,
                            current_monthly_requests=new_monthly_requests,
                            current_daily_tokens=new_daily_tokens,
                            current_monthly_tokens=new_monthly_tokens,
                            current_daily_spend=float(new_daily_spend),
                            current_monthly_spend=float(new_monthly_spend),
                            version=CommunityServerLLMConfig.version + 1,
                        )
                    )
                    update_result = await self.db.execute(update_stmt)

                    if update_result.rowcount == 0:  # type: ignore
                        continue

                return True, None

            except Exception:
                raise

        return False, "Failed to reserve usage after multiple attempts due to version conflicts"

    async def record_usage(
        self,
        community_server_id: UUID,
        provider: str,
        tokens_used: int,
        model: str,
        success: bool = True,
        error_message: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: Decimal | None = None,
    ) -> None:
        """
        Record an LLM API usage event.

        Updates counters and creates an audit log entry.

        Args:
            community_server_id: Community server UUID
            provider: Provider name
            tokens_used: Number of tokens consumed (total)
            model: Model used for the request
            success: Whether the request succeeded
            error_message: Error message if request failed
            input_tokens: Number of input tokens (if available)
            output_tokens: Number of output tokens (if available)
            cost_usd: Pre-calculated cost (optional, calculated if not provided)
        """
        config = await self._get_config(community_server_id, provider)
        if not config:
            return

        # Calculate cost if not provided
        if cost_usd is None:
            try:
                if input_tokens is not None and output_tokens is not None:
                    cost_usd = await LLMCostCalculator.calculate_cost_async(
                        provider, model, input_tokens, output_tokens
                    )
                else:
                    cost_usd = await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                        provider, model, tokens_used
                    )
            except ValueError:
                # Unknown model or provider - set cost to 0
                cost_usd = Decimal("0.000000")

        # Update usage counters including cost
        update_values = {
            "current_daily_requests": CommunityServerLLMConfig.current_daily_requests + 1,
            "current_monthly_requests": CommunityServerLLMConfig.current_monthly_requests + 1,
            "current_daily_tokens": CommunityServerLLMConfig.current_daily_tokens + tokens_used,
            "current_monthly_tokens": CommunityServerLLMConfig.current_monthly_tokens + tokens_used,
            "current_daily_spend": CommunityServerLLMConfig.current_daily_spend + float(cost_usd),
            "current_monthly_spend": CommunityServerLLMConfig.current_monthly_spend
            + float(cost_usd),
        }

        await self.db.execute(
            update(CommunityServerLLMConfig)
            .where(CommunityServerLLMConfig.id == config.id)
            .values(**update_values)
        )

        usage_log = LLMUsageLog(
            community_server_id=community_server_id,
            provider=provider,
            model=model,
            tokens_used=tokens_used,
            cost_usd=float(cost_usd),
            success=success,
            error_message=error_message,
            timestamp=datetime.now(UTC),
        )
        self.db.add(usage_log)
        await self.db.commit()

    async def check_and_record_usage(  # noqa: PLR0912
        self,
        community_server_id: UUID,
        provider: str,
        tokens_used: int,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """
        Atomically check limits and record usage in a single transaction.

        Atomic checking with transaction management and comprehensive validation.

        This method prevents race conditions by using SELECT FOR UPDATE to lock
        the configuration row, checking limits, and updating counters atomically.
        Uses optimistic locking with version numbers for additional safety.

        Args:
            community_server_id: Community server UUID
            provider: Provider name
            tokens_used: Number of tokens consumed (total)
            model: Model used for the request
            input_tokens: Number of input tokens (if available)
            output_tokens: Number of output tokens (if available)

        Raises:
            LLMUsageLimitExceeded: If any usage limit would be exceeded
            ValueError: If provider not configured or disabled

        Example:
            try:
                await tracker.check_and_record_usage(
                    community_server_id=uuid,
                    provider="openai",
                    tokens_used=1000,
                    model="gpt-5.1",
                    input_tokens=750,
                    output_tokens=250
                )
            except LLMUsageLimitExceeded as e:
                # Handle limit exceeded
                raise HTTPException(status_code=429, detail=str(e))
        """
        max_retries = 3
        for _attempt in range(max_retries):
            try:
                # Use begin_nested() if already in a transaction (e.g., in tests)
                # Otherwise use begin() to start a new transaction
                if self.db.in_transaction():
                    transaction = self.db.begin_nested()
                else:
                    transaction = self.db.begin()

                async with transaction:
                    stmt = (
                        select(CommunityServerLLMConfig)
                        .where(
                            CommunityServerLLMConfig.community_server_id == community_server_id,
                            CommunityServerLLMConfig.provider == provider,
                        )
                        .with_for_update()
                    )
                    result = await self.db.execute(stmt)
                    config = result.scalar_one_or_none()

                    if not config or not config.enabled:
                        raise ValueError("Provider not configured or disabled")

                    await self._reset_counters_if_needed_in_transaction(config)

                    await self.db.refresh(config)

                    # Calculate cost
                    try:
                        if input_tokens is not None and output_tokens is not None:
                            cost_usd = await LLMCostCalculator.calculate_cost_async(
                                provider, model, input_tokens, output_tokens
                            )
                        else:
                            cost_usd = (
                                await LLMCostCalculator.calculate_cost_from_total_tokens_async(
                                    provider, model, tokens_used
                                )
                            )
                    except ValueError:
                        # Unknown model or provider - set cost to 0
                        cost_usd = Decimal("0.000000")

                    new_daily_requests = config.current_daily_requests + 1
                    new_monthly_requests = config.current_monthly_requests + 1
                    new_daily_tokens = config.current_daily_tokens + tokens_used
                    new_monthly_tokens = config.current_monthly_tokens + tokens_used
                    new_daily_spend = Decimal(str(config.current_daily_spend)) + cost_usd
                    new_monthly_spend = Decimal(str(config.current_monthly_spend)) + cost_usd

                    if (
                        config.daily_request_limit
                        and new_daily_requests > config.daily_request_limit
                    ):
                        raise LLMUsageLimitExceeded(
                            f"Daily request limit reached ({config.daily_request_limit})"
                        )

                    if (
                        config.monthly_request_limit
                        and new_monthly_requests > config.monthly_request_limit
                    ):
                        raise LLMUsageLimitExceeded(
                            f"Monthly request limit reached ({config.monthly_request_limit})"
                        )

                    if config.daily_token_limit and new_daily_tokens > config.daily_token_limit:
                        raise LLMUsageLimitExceeded("Daily token limit would be exceeded")

                    if (
                        config.monthly_token_limit
                        and new_monthly_tokens > config.monthly_token_limit
                    ):
                        raise LLMUsageLimitExceeded("Monthly token limit would be exceeded")

                    if config.daily_spend_limit:
                        daily_limit = Decimal(str(config.daily_spend_limit))
                        if new_daily_spend > daily_limit:
                            raise LLMUsageLimitExceeded(
                                f"Daily spending limit would be exceeded (${daily_limit})"
                            )

                    if config.monthly_spend_limit:
                        monthly_limit = Decimal(str(config.monthly_spend_limit))
                        if new_monthly_spend > monthly_limit:
                            raise LLMUsageLimitExceeded(
                                f"Monthly spending limit would be exceeded (${monthly_limit})"
                            )

                    update_stmt = (
                        update(CommunityServerLLMConfig)
                        .where(
                            CommunityServerLLMConfig.id == config.id,
                            CommunityServerLLMConfig.version == config.version,
                        )
                        .values(
                            current_daily_requests=new_daily_requests,
                            current_monthly_requests=new_monthly_requests,
                            current_daily_tokens=new_daily_tokens,
                            current_monthly_tokens=new_monthly_tokens,
                            current_daily_spend=float(new_daily_spend),
                            current_monthly_spend=float(new_monthly_spend),
                            version=CommunityServerLLMConfig.version + 1,
                        )
                    )
                    update_result = await self.db.execute(update_stmt)

                    if update_result.rowcount == 0:  # type: ignore
                        continue

                    usage_log = LLMUsageLog(
                        community_server_id=community_server_id,
                        provider=provider,
                        model=model,
                        tokens_used=tokens_used,
                        cost_usd=float(cost_usd),
                        success=True,
                        error_message=None,
                        timestamp=datetime.now(UTC),
                    )
                    self.db.add(usage_log)

                return

            except (LLMUsageLimitExceeded, ValueError):
                raise

        raise RuntimeError(
            f"Failed to record usage after {max_retries} attempts due to version conflicts"
        )

    async def _reset_counters_if_needed_in_transaction(
        self, config: CommunityServerLLMConfig
    ) -> None:
        """
        Reset usage counters if the period has passed (in-transaction version).

        This is a helper for check_and_record_usage() that doesn't commit.
        Modifies the config object in-place.

        Args:
            config: LLM configuration to check and update
        """
        now = datetime.now(UTC)
        updates: dict[str, Any] = {}

        def _should_reset_daily() -> bool:
            if not config.last_daily_reset:
                return True
            return now - config.last_daily_reset > timedelta(days=1)

        def _should_reset_monthly() -> bool:
            if not config.last_monthly_reset:
                return True
            return now - config.last_monthly_reset > timedelta(days=30)

        if _should_reset_daily():
            config.current_daily_requests = 0
            config.current_daily_tokens = 0
            config.current_daily_spend = 0.0
            config.last_daily_reset = now
            updates["current_daily_requests"] = 0
            updates["current_daily_tokens"] = 0
            updates["current_daily_spend"] = 0.0
            updates["last_daily_reset"] = now

        if _should_reset_monthly():
            config.current_monthly_requests = 0
            config.current_monthly_tokens = 0
            config.current_monthly_spend = 0.0
            config.last_monthly_reset = now
            updates["current_monthly_requests"] = 0
            updates["current_monthly_tokens"] = 0
            updates["current_monthly_spend"] = 0.0
            updates["last_monthly_reset"] = now

        if updates:
            await self.db.execute(
                update(CommunityServerLLMConfig)
                .where(CommunityServerLLMConfig.id == config.id)
                .values(**updates)
            )
            await self.db.flush()

    async def _get_config(
        self, community_server_id: UUID, provider: str
    ) -> CommunityServerLLMConfig | None:
        """
        Get LLM configuration for a community server and provider.

        Args:
            community_server_id: Community server UUID
            provider: Provider name

        Returns:
            Configuration object, or None if not found
        """
        result = await self.db.execute(
            select(CommunityServerLLMConfig).where(
                CommunityServerLLMConfig.community_server_id == community_server_id,
                CommunityServerLLMConfig.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def _reset_counters_if_needed(self, config: CommunityServerLLMConfig) -> None:
        """
        Reset usage counters if the period has passed.

        Args:
            config: LLM configuration to check and update
        """
        now = datetime.now(UTC)
        needs_update = False
        updates: dict[str, Any] = {}

        if not config.last_daily_reset or (now - config.last_daily_reset > timedelta(days=1)):
            updates["current_daily_requests"] = 0
            updates["current_daily_tokens"] = 0
            updates["current_daily_spend"] = 0.0
            updates["last_daily_reset"] = now
            needs_update = True

        if not config.last_monthly_reset or (now - config.last_monthly_reset > timedelta(days=30)):
            updates["current_monthly_requests"] = 0
            updates["current_monthly_tokens"] = 0
            updates["current_monthly_spend"] = 0.0
            updates["last_monthly_reset"] = now
            needs_update = True

        if needs_update:
            await self.db.execute(
                update(CommunityServerLLMConfig)
                .where(CommunityServerLLMConfig.id == config.id)
                .values(**updates)
            )
            await self.db.commit()
            await self.db.refresh(config)

    async def get_usage_stats(
        self, community_server_id: UUID, provider: str
    ) -> dict[str, Any] | None:
        """
        Get current usage statistics for a community server and provider.

        Args:
            community_server_id: Community server UUID
            provider: Provider name

        Returns:
            Dictionary with usage statistics, or None if not configured
        """
        config = await self._get_config(community_server_id, provider)
        if not config:
            return None

        await self._reset_counters_if_needed(config)

        return {
            "provider": provider,
            "daily_requests": {
                "current": config.current_daily_requests,
                "limit": config.daily_request_limit,
                "percentage": (
                    (config.current_daily_requests / config.daily_request_limit * 100)
                    if config.daily_request_limit
                    else None
                ),
            },
            "monthly_requests": {
                "current": config.current_monthly_requests,
                "limit": config.monthly_request_limit,
                "percentage": (
                    (config.current_monthly_requests / config.monthly_request_limit * 100)
                    if config.monthly_request_limit
                    else None
                ),
            },
            "daily_tokens": {
                "current": config.current_daily_tokens,
                "limit": config.daily_token_limit,
                "percentage": (
                    (config.current_daily_tokens / config.daily_token_limit * 100)
                    if config.daily_token_limit
                    else None
                ),
            },
            "monthly_tokens": {
                "current": config.current_monthly_tokens,
                "limit": config.monthly_token_limit,
                "percentage": (
                    (config.current_monthly_tokens / config.monthly_token_limit * 100)
                    if config.monthly_token_limit
                    else None
                ),
            },
            "daily_spend": {
                "current": float(config.current_daily_spend),
                "limit": float(config.daily_spend_limit) if config.daily_spend_limit else None,
                "percentage": (
                    (float(config.current_daily_spend) / float(config.daily_spend_limit) * 100)
                    if config.daily_spend_limit
                    else None
                ),
            },
            "monthly_spend": {
                "current": float(config.current_monthly_spend),
                "limit": float(config.monthly_spend_limit) if config.monthly_spend_limit else None,
                "percentage": (
                    (float(config.current_monthly_spend) / float(config.monthly_spend_limit) * 100)
                    if config.monthly_spend_limit
                    else None
                ),
            },
            "last_daily_reset": config.last_daily_reset,
            "last_monthly_reset": config.last_monthly_reset,
        }
