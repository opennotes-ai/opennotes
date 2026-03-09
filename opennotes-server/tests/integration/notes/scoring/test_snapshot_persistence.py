import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.notes.scoring.models import ScoringSnapshot
from src.notes.scoring.snapshot_persistence import persist_scoring_snapshot

pytestmark = pytest.mark.integration


@pytest.fixture
async def community_server() -> CommunityServer:
    async with get_session_maker()() as session:
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id=f"test-{uuid4().hex[:8]}",
            name="Snapshot Test Server",
            is_active=True,
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)
        return server


class TestPersistScoringSnapshotUpsert:
    @pytest.mark.asyncio
    async def test_upsert_creates_new_snapshot(self, community_server: CommunityServer):
        rater_factors = [{"rater_id": "r1", "intercept": 0.5, "factor1": -0.2}]
        note_factors = [{"note_id": "n1", "intercept": 0.7, "factor1": 0.1}]
        metadata = {"tier": "intermediate", "scorer_name": "MFCoreScorer"}

        async with get_session_maker()() as session:
            await persist_scoring_snapshot(
                community_server_id=community_server.id,
                rater_factors=rater_factors,
                note_factors=note_factors,
                global_intercept=0.42,
                metadata=metadata,
                db=session,
            )
            await session.commit()

        async with get_session_maker()() as session:
            count = (
                await session.execute(
                    select(func.count(ScoringSnapshot.id)).where(
                        ScoringSnapshot.community_server_id == community_server.id
                    )
                )
            ).scalar()
            assert count == 1

            row = (
                await session.execute(
                    select(ScoringSnapshot).where(
                        ScoringSnapshot.community_server_id == community_server.id
                    )
                )
            ).scalar_one()
            assert row.global_intercept == pytest.approx(0.42)
            assert row.rater_factors == rater_factors
            assert row.note_factors == note_factors

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_snapshot(self, community_server: CommunityServer):
        rater_factors_v1 = [{"rater_id": "r1", "intercept": 0.5, "factor1": -0.2}]
        note_factors_v1 = [{"note_id": "n1", "intercept": 0.7, "factor1": 0.1}]
        metadata_v1 = {"tier": "intermediate", "scorer_name": "MFCoreScorer"}

        async with get_session_maker()() as session:
            await persist_scoring_snapshot(
                community_server_id=community_server.id,
                rater_factors=rater_factors_v1,
                note_factors=note_factors_v1,
                global_intercept=0.42,
                metadata=metadata_v1,
                db=session,
            )
            await session.commit()

        rater_factors_v2 = [{"rater_id": "r1", "intercept": 0.9, "factor1": 0.3}]
        note_factors_v2 = [{"note_id": "n2", "intercept": -0.1, "factor1": 0.5}]
        metadata_v2 = {"tier": "full", "scorer_name": "MFCoreScorer"}

        async with get_session_maker()() as session:
            await persist_scoring_snapshot(
                community_server_id=community_server.id,
                rater_factors=rater_factors_v2,
                note_factors=note_factors_v2,
                global_intercept=0.88,
                metadata=metadata_v2,
                db=session,
            )
            await session.commit()

        async with get_session_maker()() as session:
            count = (
                await session.execute(
                    select(func.count(ScoringSnapshot.id)).where(
                        ScoringSnapshot.community_server_id == community_server.id
                    )
                )
            ).scalar()
            assert count == 1

            row = (
                await session.execute(
                    select(ScoringSnapshot).where(
                        ScoringSnapshot.community_server_id == community_server.id
                    )
                )
            ).scalar_one()
            assert row.global_intercept == pytest.approx(0.88)
            assert row.rater_factors == rater_factors_v2
            assert row.note_factors == note_factors_v2

    @pytest.mark.asyncio
    async def test_concurrent_upserts_no_integrity_error(self, community_server: CommunityServer):
        async def do_upsert(intercept: float):
            async with get_session_maker()() as session:
                await persist_scoring_snapshot(
                    community_server_id=community_server.id,
                    rater_factors=[{"rater_id": "r1", "intercept": intercept, "factor1": 0.0}],
                    note_factors=[],
                    global_intercept=intercept,
                    metadata={"run": intercept},
                    db=session,
                )
                await session.commit()

        tasks = [do_upsert(float(i)) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, f"Concurrent upserts raised exceptions: {errors}"

        async with get_session_maker()() as session:
            count = (
                await session.execute(
                    select(func.count(ScoringSnapshot.id)).where(
                        ScoringSnapshot.community_server_id == community_server.id
                    )
                )
            ).scalar()
            assert count == 1

    @pytest.mark.asyncio
    async def test_upsert_does_not_require_select(self, community_server: CommunityServer):
        original_execute = None

        async def tracking_execute(stmt, *args, **kwargs):
            sql_text = str(stmt)
            if sql_text.strip().upper().startswith("SELECT") and "scoring_snapshots" in sql_text:
                raise AssertionError("persist_scoring_snapshot should not issue a SELECT query")
            return await original_execute(stmt, *args, **kwargs)  # type: ignore[misc]

        async with get_session_maker()() as session:
            original_execute = session.execute
            session.execute = tracking_execute  # type: ignore[assignment]

            await persist_scoring_snapshot(
                community_server_id=community_server.id,
                rater_factors=[],
                note_factors=[],
                global_intercept=0.0,
                metadata={},
                db=session,
            )
            await session.commit()
