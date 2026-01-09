"""Integration tests for LLM usage tracker concurrency and race condition handling."""

import asyncio
import base64
import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.encryption import EncryptionService
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.llm_config.usage_tracker import LLMUsageLimitExceeded, LLMUsageTracker


def _generate_test_key() -> str:
    """Generate a valid test encryption key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture
def encryption_service() -> EncryptionService:
    """Create encryption service for tests."""
    return EncryptionService(_generate_test_key())


@pytest.fixture
async def community_server() -> CommunityServer:
    """Create a test community server."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id="test-guild-123",
            name="Test Server",
            is_active=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


@pytest.fixture
async def llm_config_with_limit(
    community_server: CommunityServer,
    encryption_service: EncryptionService,
) -> CommunityServerLLMConfig:
    """Create an LLM config with strict limits for testing."""
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        encrypted_key, key_id, preview = encryption_service.encrypt_api_key("sk-test-key-12345")

        now = datetime.now(UTC)
        config = CommunityServerLLMConfig(
            community_server_id=community_server.id,
            provider="openai",
            api_key_encrypted=encrypted_key,
            encryption_key_id=key_id,
            api_key_preview=preview,
            enabled=True,
            settings={"model": "gpt-5.1"},
            daily_request_limit=10,
            monthly_request_limit=100,
            daily_token_limit=10000,
            monthly_token_limit=100000,
            current_daily_requests=0,
            current_monthly_requests=0,
            current_daily_tokens=0,
            current_monthly_tokens=0,
            last_daily_reset=now,
            last_monthly_reset=now,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config


class TestConcurrentUsageTracking:
    """Test concurrent usage tracking to verify race condition is fixed."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_respect_limit(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that concurrent requests cannot bypass the rate limit."""
        from src.database import get_session_maker

        limit = llm_config_with_limit.daily_request_limit
        concurrent_requests = 20

        async def make_request(request_num: int) -> tuple[int, Exception | None]:
            """Attempt to record usage and return result."""
            # Create separate session for each concurrent request
            async with get_session_maker()() as session:
                tracker = LLMUsageTracker(session)
                try:
                    await tracker.check_and_record_usage(
                        community_server_id=community_server.id,
                        provider="openai",
                        tokens_used=100,
                        model="gpt-5.1",
                    )
                    await session.commit()
                    return (request_num, None)
                except (LLMUsageLimitExceeded, ValueError) as e:
                    await session.rollback()
                    return (request_num, e)

        tasks = [make_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, tuple) and r[1] is None]
        failures = [r for r in results if isinstance(r, tuple) and r[1] is not None]
        exceptions = [r for r in results if not isinstance(r, tuple)]

        assert len(exceptions) == 0, f"Unexpected exceptions in concurrent tasks: {exceptions}"
        assert len(successes) == limit, (
            f"Expected exactly {limit} successful requests, got {len(successes)}. "
            f"This indicates a race condition!"
        )
        assert len(failures) == concurrent_requests - limit

        # Capture ID before expiring to avoid lazy load issues
        config_id = llm_config_with_limit.id

        # Expire all objects to force fresh data from database
        # (concurrent sessions may have committed changes)
        db_session.expire_all()

        stmt = select(CommunityServerLLMConfig).where(CommunityServerLLMConfig.id == config_id)
        result = await db_session.execute(stmt)
        final_config = result.scalar_one()

        assert final_config.current_daily_requests == limit, (
            f"Expected current_daily_requests to be {limit}, "
            f"got {final_config.current_daily_requests}. Race condition detected!"
        )

        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_concurrent_token_limit_enforcement(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that concurrent requests cannot exceed token limits."""
        from src.database import get_session_maker

        token_limit = llm_config_with_limit.daily_token_limit
        tokens_per_request = 2000
        concurrent_requests = 10

        async def make_request(request_num: int) -> tuple[int, Exception | None]:
            """Attempt to record usage and return result."""
            # Create separate session for each concurrent request
            async with get_session_maker()() as session:
                tracker = LLMUsageTracker(session)
                try:
                    await tracker.check_and_record_usage(
                        community_server_id=community_server.id,
                        provider="openai",
                        tokens_used=tokens_per_request,
                        model="gpt-5.1",
                    )
                    await session.commit()
                    return (request_num, None)
                except (LLMUsageLimitExceeded, ValueError) as e:
                    await session.rollback()
                    return (request_num, e)

        tasks = [make_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, tuple) and r[1] is None]
        exceptions = [r for r in results if not isinstance(r, tuple)]

        assert len(exceptions) == 0, f"Unexpected exceptions in concurrent tasks: {exceptions}"

        expected_successes = token_limit // tokens_per_request
        assert len(successes) == expected_successes, (
            f"Expected exactly {expected_successes} successful requests, "
            f"got {len(successes)}. Token limit race condition!"
        )

        # Capture ID before expiring to avoid lazy load issues
        config_id = llm_config_with_limit.id

        # Expire all objects to force fresh data from database
        db_session.expire_all()

        stmt = select(CommunityServerLLMConfig).where(CommunityServerLLMConfig.id == config_id)
        result = await db_session.execute(stmt)
        final_config = result.scalar_one()

        expected_tokens = expected_successes * tokens_per_request
        assert final_config.current_daily_tokens == expected_tokens, (
            f"Expected current_daily_tokens to be {expected_tokens}, "
            f"got {final_config.current_daily_tokens}. Race condition in token tracking!"
        )

    @pytest.mark.asyncio
    async def test_optimistic_locking_version_increments(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that version number increments correctly with concurrent updates."""
        from src.database import get_session_maker

        initial_version = llm_config_with_limit.version
        num_requests = 5

        async def make_request(request_num: int) -> None:
            """Make a successful request."""
            # Create separate session for each concurrent request
            async with get_session_maker()() as session:
                tracker = LLMUsageTracker(session)
                await tracker.check_and_record_usage(
                    community_server_id=community_server.id,
                    provider="openai",
                    tokens_used=100,
                    model="gpt-5.1",
                )
                await session.commit()

        tasks = [make_request(i) for i in range(num_requests)]
        await asyncio.gather(*tasks)

        # Capture ID before expiring to avoid lazy load issues
        config_id = llm_config_with_limit.id

        # Expire all objects to force fresh data from database
        db_session.expire_all()

        stmt = select(CommunityServerLLMConfig).where(CommunityServerLLMConfig.id == config_id)
        result = await db_session.execute(stmt)
        final_config = result.scalar_one()

        assert final_config.version == initial_version + num_requests, (
            f"Expected version to be {initial_version + num_requests}, "
            f"got {final_config.version}. Version tracking failed!"
        )

    @pytest.mark.asyncio
    async def test_disabled_provider_raises_error(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that disabled provider raises ValueError."""
        llm_config_with_limit.enabled = False
        db_session.add(llm_config_with_limit)
        await db_session.commit()

        tracker = LLMUsageTracker(db_session)

        with pytest.raises(ValueError, match="Provider not configured or disabled"):
            await tracker.check_and_record_usage(
                community_server_id=community_server.id,
                provider="openai",
                tokens_used=100,
                model="gpt-5.1",
            )

    @pytest.mark.asyncio
    async def test_nonexistent_provider_raises_error(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
    ) -> None:
        """Test that nonexistent provider raises ValueError."""
        tracker = LLMUsageTracker(db_session)

        with pytest.raises(ValueError, match="Provider not configured or disabled"):
            await tracker.check_and_record_usage(
                community_server_id=community_server.id,
                provider="nonexistent",
                tokens_used=100,
                model="gpt-5.1",
            )

    @pytest.mark.asyncio
    async def test_monthly_limit_enforcement(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that monthly limits are enforced correctly."""
        llm_config_with_limit.current_monthly_requests = 99
        db_session.add(llm_config_with_limit)
        await db_session.commit()

        tracker = LLMUsageTracker(db_session)

        await tracker.check_and_record_usage(
            community_server_id=community_server.id,
            provider="openai",
            tokens_used=100,
            model="gpt-5.1",
        )

        with pytest.raises(LLMUsageLimitExceeded, match="Monthly request limit reached"):
            await tracker.check_and_record_usage(
                community_server_id=community_server.id,
                provider="openai",
                tokens_used=100,
                model="gpt-5.1",
            )

    @pytest.mark.asyncio
    async def test_usage_log_created_on_success(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Test that usage logs are created for successful requests."""
        from src.llm_config.models import LLMUsageLog

        tracker = LLMUsageTracker(db_session)

        await tracker.check_and_record_usage(
            community_server_id=community_server.id,
            provider="openai",
            tokens_used=500,
            model="gpt-5.1",
        )

        stmt = select(LLMUsageLog).where(
            LLMUsageLog.community_server_id == community_server.id,
            LLMUsageLog.provider == "openai",
        )
        result = await db_session.execute(stmt)
        logs = result.scalars().all()

        assert len(logs) == 1
        assert logs[0].tokens_used == 500
        assert logs[0].model == "gpt-5.1"
        assert logs[0].success is True
        assert logs[0].error_message is None

    @pytest.mark.asyncio
    async def test_stress_test_high_concurrency(
        self,
        db_session: AsyncSession,
        community_server: CommunityServer,
        llm_config_with_limit: CommunityServerLLMConfig,
    ) -> None:
        """Stress test with high concurrency to catch race conditions."""
        from src.database import get_session_maker

        limit = 50
        llm_config_with_limit.daily_request_limit = limit
        db_session.add(llm_config_with_limit)
        await db_session.commit()

        concurrent_requests = 100

        async def make_request(request_num: int) -> tuple[int, Exception | None]:
            """Attempt to record usage."""
            # Create separate session for each concurrent request
            async with get_session_maker()() as session:
                tracker = LLMUsageTracker(session)
                try:
                    await tracker.check_and_record_usage(
                        community_server_id=community_server.id,
                        provider="openai",
                        tokens_used=10,
                        model="gpt-5.1",
                    )
                    await session.commit()
                    return (request_num, None)
                except (LLMUsageLimitExceeded, ValueError) as e:
                    await session.rollback()
                    return (request_num, e)

        tasks = [make_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if isinstance(r, tuple) and r[1] is None]
        exceptions = [r for r in results if not isinstance(r, tuple)]

        assert len(exceptions) == 0, f"Unexpected exceptions in concurrent tasks: {exceptions}"

        assert len(successes) == limit, (
            f"STRESS TEST FAILED: Expected exactly {limit} successes, "
            f"got {len(successes)}. Race condition detected under high load!"
        )

        # Capture ID before expiring to avoid lazy load issues
        config_id = llm_config_with_limit.id

        # Expire all objects to force fresh data from database
        db_session.expire_all()

        stmt = select(CommunityServerLLMConfig).where(CommunityServerLLMConfig.id == config_id)
        result = await db_session.execute(stmt)
        final_config = result.scalar_one()

        assert final_config.current_daily_requests == limit, (
            f"STRESS TEST FAILED: Final count is {final_config.current_daily_requests}, "
            f"expected {limit}. Critical race condition!"
        )
