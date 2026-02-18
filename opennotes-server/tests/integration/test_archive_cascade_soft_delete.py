from uuid import uuid4

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.message_archive_service import MessageArchiveService
from src.notes.models import Note, Rating, Request
from src.users.profile_models import UserProfile


class TestCascadeSoftDelete:
    @pytest.mark.asyncio
    async def test_cascade_soft_delete_archive_only_no_request(self):
        async with get_session_maker()() as db:
            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="orphaned archive",
            )
            db.add(archive)
            await db.flush()
            archive_id = archive.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_id"] is None
        assert result["request_deleted"] is False
        assert result["note_id"] is None
        assert result["note_deleted"] is False
        assert result["skipped_reason"] is None
        assert result["dry_run"] is False

        async with get_session_maker()() as db:
            stmt = select(MessageArchive).where(MessageArchive.id == archive_id)
            row = (await db.execute(stmt)).scalar_one()
            assert row.deleted_at is not None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_system_request_no_note(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-csdn-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="short",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-csdn-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                note_id=None,
            )
            db.add(request)
            await db.flush()
            archive_id = archive.id
            request_id_str = request.request_id
            request_pk = request.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_id"] == request_id_str
        assert result["request_deleted"] is True
        assert result["note_deleted"] is False
        assert result["skipped_reason"] is None

        async with get_session_maker()() as db:
            stmt = select(Request).where(Request.id == request_pk)
            row = (await db.execute(stmt)).scalar_one()
            assert row.deleted_at is not None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_system_request_with_unrated_ai_note(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-csun-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            user_profile = UserProfile(
                display_name="AI Author",
            )
            db.add(user_profile)
            await db.flush()

            note = Note(
                author_id=user_profile.id,
                community_server_id=community_server.id,
                summary="AI generated note",
                classification="NOT_MISLEADING",
                ai_generated=True,
            )
            db.add(note)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="bad match",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-csun-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                note_id=note.id,
            )
            db.add(request)
            await db.flush()

            archive_id = archive.id
            request_pk = request.id
            note_id = note.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_deleted"] is True
        assert result["note_deleted"] is True
        assert result["note_id"] == str(note_id)
        assert result["skipped_reason"] is None

        async with get_session_maker()() as db:
            a = (
                await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
            ).scalar_one()
            r = (await db.execute(select(Request).where(Request.id == request_pk))).scalar_one()
            n = (await db.execute(select(Note).where(Note.id == note_id))).scalar_one()
            assert a.deleted_at is not None
            assert r.deleted_at is not None
            assert n.deleted_at is not None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_system_request_with_rated_ai_note(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-csra-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            author = UserProfile(display_name="AI Author")
            rater = UserProfile(display_name="Rater")
            db.add_all([author, rater])
            await db.flush()

            note = Note(
                author_id=author.id,
                community_server_id=community_server.id,
                summary="Rated AI note",
                classification="NOT_MISLEADING",
                ai_generated=True,
            )
            db.add(note)
            await db.flush()

            rating = Rating(
                rater_id=rater.id,
                note_id=note.id,
                helpfulness_level="HELPFUL",
            )
            db.add(rating)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="matched content",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-csra-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                note_id=note.id,
            )
            db.add(request)
            await db.flush()

            archive_id = archive.id
            request_pk = request.id
            note_id = note.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_deleted"] is False
        assert result["note_deleted"] is False
        assert result["skipped_reason"] == "rated_ai_note"

        async with get_session_maker()() as db:
            a = (
                await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
            ).scalar_one()
            r = (await db.execute(select(Request).where(Request.id == request_pk))).scalar_one()
            n = (await db.execute(select(Note).where(Note.id == note_id))).scalar_one()
            assert a.deleted_at is not None
            assert r.deleted_at is None
            assert n.deleted_at is None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_non_system_request(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-csnsr-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="user submitted",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-csnsr-{uuid4().hex[:8]}",
                requested_by="user-12345",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
            )
            db.add(request)
            await db.flush()

            archive_id = archive.id
            request_pk = request.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_deleted"] is False
        assert result["skipped_reason"] == "non_system_request"

        async with get_session_maker()() as db:
            a = (
                await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
            ).scalar_one()
            r = (await db.execute(select(Request).where(Request.id == request_pk))).scalar_one()
            assert a.deleted_at is not None
            assert r.deleted_at is None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_system_request_with_human_note(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-cshn-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            author = UserProfile(display_name="Human Author")
            db.add(author)
            await db.flush()

            note = Note(
                author_id=author.id,
                community_server_id=community_server.id,
                summary="Human written note",
                classification="MISINFORMED_OR_POTENTIALLY_MISLEADING",
                ai_generated=False,
            )
            db.add(note)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="matched content",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-cshn-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                note_id=note.id,
            )
            db.add(request)
            await db.flush()

            archive_id = archive.id
            request_pk = request.id
            note_id = note.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_deleted"] is False
        assert result["note_deleted"] is False
        assert result["skipped_reason"] == "human_note"

        async with get_session_maker()() as db:
            a = (
                await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
            ).scalar_one()
            r = (await db.execute(select(Request).where(Request.id == request_pk))).scalar_one()
            n = (await db.execute(select(Note).where(Note.id == note_id))).scalar_one()
            assert a.deleted_at is not None
            assert r.deleted_at is None
            assert n.deleted_at is None

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_dry_run(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-csdr-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            author = UserProfile(display_name="AI Author Dry")
            db.add(author)
            await db.flush()

            note = Note(
                author_id=author.id,
                community_server_id=community_server.id,
                summary="Dry run note",
                classification="NOT_MISLEADING",
                ai_generated=True,
            )
            db.add(note)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="dry run content",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-csdr-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                note_id=note.id,
            )
            db.add(request)
            await db.flush()

            archive_id = archive.id
            request_pk = request.id
            note_id = note.id

            result = await MessageArchiveService.cascade_soft_delete(db, archive_id, dry_run=True)
            await db.commit()

        assert result["archive_deleted"] is True
        assert result["request_deleted"] is True
        assert result["note_deleted"] is True
        assert result["dry_run"] is True

        async with get_session_maker()() as db:
            a = (
                await db.execute(select(MessageArchive).where(MessageArchive.id == archive_id))
            ).scalar_one()
            r = (await db.execute(select(Request).where(Request.id == request_pk))).scalar_one()
            n = (await db.execute(select(Note).where(Note.id == note_id))).scalar_one()
            assert a.deleted_at is None
            assert r.deleted_at is None
            assert n.deleted_at is None


class TestFindBadArchives:
    @pytest.mark.asyncio
    async def test_find_bad_archives_short_content(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-fba-sc-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="hi",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-fba-sc-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
            )
            db.add(request)
            await db.flush()
            archive_id = archive.id
            await db.commit()

        async with get_session_maker()() as db:
            bad_ids = await MessageArchiveService.find_bad_archives(db)
            assert archive_id in bad_ids

    @pytest.mark.asyncio
    async def test_find_bad_archives_low_similarity(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-fba-ls-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="this is a sufficiently long content string for testing",
            )
            db.add(archive)
            await db.flush()

            request = Request(
                request_id=f"req-fba-ls-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
                similarity_score=0.3,
            )
            db.add(request)
            await db.flush()
            archive_id = archive.id
            await db.commit()

        async with get_session_maker()() as db:
            bad_ids = await MessageArchiveService.find_bad_archives(db)
            assert archive_id in bad_ids

    @pytest.mark.asyncio
    async def test_find_bad_archives_excludes_already_deleted(self):
        async with get_session_maker()() as db:
            community_server = CommunityServer(
                platform="discord",
                platform_community_server_id=f"guild-fba-del-{uuid4().hex[:8]}",
                name="Test",
            )
            db.add(community_server)
            await db.flush()

            archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text="hi",
            )
            db.add(archive)
            await db.flush()
            archive.soft_delete()
            await db.flush()

            request = Request(
                request_id=f"req-fba-del-{uuid4().hex[:8]}",
                requested_by="system-fact-check",
                community_server_id=community_server.id,
                message_archive_id=archive.id,
            )
            db.add(request)
            await db.flush()
            archive_id = archive.id
            await db.commit()

        async with get_session_maker()() as db:
            bad_ids = await MessageArchiveService.find_bad_archives(db)
            assert archive_id not in bad_ids
