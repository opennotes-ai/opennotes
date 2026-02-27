from uuid import uuid4

import pytest
from sqlalchemy import select

from src.llm_config.models import CommunityServer
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.models import Note, Rating, Request
from src.simulation.models import SimulationOrchestrator, SimulationRun
from src.simulation.scoring_integration import trigger_scoring_for_simulation
from src.users.profile_models import UserProfile


@pytest.fixture
async def scoring_community(db):
    server = CommunityServer(
        id=uuid4(),
        platform="playground",
        platform_community_server_id=f"scoring-test-{uuid4().hex[:8]}",
        name="Scoring Test Server",
        is_active=True,
    )
    db.add(server)
    await db.flush()
    return server


@pytest.fixture
async def scoring_sim_run(db, scoring_community):
    orchestrator = SimulationOrchestrator(
        name=f"test-orch-{uuid4().hex[:8]}",
        community_server_id=scoring_community.id,
    )
    db.add(orchestrator)
    await db.flush()

    run = SimulationRun(
        orchestrator_id=orchestrator.id,
        community_server_id=scoring_community.id,
        status="running",
    )
    db.add(run)
    await db.flush()
    return run


@pytest.fixture
async def make_note_with_ratings(db, scoring_community):
    async def _make(rating_count=6, with_request=True):
        author = UserProfile(display_name=f"author-{uuid4().hex[:6]}")
        db.add(author)
        await db.flush()

        archive = None
        request = None
        if with_request:
            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="Test claim for scoring",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-{uuid4().hex[:12]}",
                community_server_id=scoring_community.id,
                message_archive_id=archive.id,
                requested_by="system-test",
                status="PENDING",
            )
            db.add(request)
            await db.flush()

        note = Note(
            author_id=author.id,
            community_server_id=scoring_community.id,
            request_id=request.request_id if request else None,
            summary="Test note summary for scoring",
            classification="NOT_MISLEADING",
            ai_generated=True,
        )
        db.add(note)
        await db.flush()

        for _ in range(rating_count):
            rater = UserProfile(display_name=f"rater-{uuid4().hex[:6]}")
            db.add(rater)
            await db.flush()

            rating = Rating(
                rater_id=rater.id,
                note_id=note.id,
                helpfulness_level="HELPFUL",
            )
            db.add(rating)

        await db.flush()
        return note, request

    return _make


@pytest.mark.asyncio
async def test_trigger_scoring_updates_status_and_score(
    db, scoring_sim_run, make_note_with_ratings
):
    note, _ = await make_note_with_ratings(rating_count=6)
    await db.commit()

    result = await trigger_scoring_for_simulation(scoring_sim_run.id, db)

    assert result.scores_computed >= 1
    assert result.note_count >= 1

    refreshed = (await db.execute(select(Note).where(Note.id == note.id))).scalar_one()
    assert refreshed.helpfulness_score > 0
    assert refreshed.status in (
        "CURRENTLY_RATED_HELPFUL",
        "CURRENTLY_RATED_NOT_HELPFUL",
        "NEEDS_MORE_RATINGS",
    )


@pytest.mark.asyncio
async def test_trigger_scoring_loads_request_without_lazy_raise(
    db, scoring_sim_run, make_note_with_ratings
):
    await make_note_with_ratings(rating_count=1, with_request=True)
    await db.commit()

    result = await trigger_scoring_for_simulation(scoring_sim_run.id, db)

    assert result.scores_computed >= 1


@pytest.mark.asyncio
async def test_trigger_scoring_transitions_request_for_helpful_note(
    db, scoring_sim_run, make_note_with_ratings
):
    note, request = await make_note_with_ratings(rating_count=6, with_request=True)
    await db.commit()

    await trigger_scoring_for_simulation(scoring_sim_run.id, db)

    refreshed_req = (
        await db.execute(select(Request).where(Request.request_id == request.request_id))
    ).scalar_one()

    refreshed_note = (await db.execute(select(Note).where(Note.id == note.id))).scalar_one()

    if refreshed_note.status == "CURRENTLY_RATED_HELPFUL":
        assert refreshed_req.status == "COMPLETED"
