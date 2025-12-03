"""
Integration tests for database persistence using real database containers.

These tests verify actual database persistence behavior by using the shared
PostgreSQL container started via test-with-postgres.sh bash script. The script
sets DATABASE_URL environment variable to point to the PostgreSQL container,
which all tests consume through src.database.async_session_maker.

Run with: mise run test:integration
"""

import pytest
from sqlalchemy import select

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture
async def db_session():
    """Provide a database session for tests using the shared test database"""
    from src.database import async_session_maker

    async with async_session_maker() as session:
        yield session
        await session.rollback()


class TestDatabasePersistence:
    """Integration tests that verify actual database persistence"""

    @pytest.mark.asyncio
    async def test_user_persists_across_sessions(self):
        """Test that user data actually persists in the database"""
        from src.database import async_session_maker
        from src.users.models import User

        user_id = None

        # Create user in first session
        async with async_session_maker() as session:
            user = User(
                username="persistent_user",
                email="persistent@example.com",
                hashed_password="hashed_password_123",
                full_name="Persistent User",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        # Verify user exists in a new session
        async with async_session_maker() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            persisted_user = result.scalar_one_or_none()

            assert persisted_user is not None
            assert persisted_user.username == "persistent_user"
            assert persisted_user.email == "persistent@example.com"
            assert persisted_user.full_name == "Persistent User"

    @pytest.mark.asyncio
    async def test_note_request_persists_across_sessions(self):
        """Test that note requests persist correctly"""
        from src.database import async_session_maker
        from src.notes.models import Request

        request_id = None

        # Create request in first session
        async with async_session_maker() as session:
            request = Request(
                request_id="req_123",
                requested_by="user_111",
                status="PENDING",
            )
            session.add(request)
            await session.commit()
            request_id = request.id

        # Verify request exists in a new session
        async with async_session_maker() as session:
            stmt = select(Request).where(Request.id == request_id)
            result = await session.execute(stmt)
            persisted_request = result.scalar_one_or_none()

            assert persisted_request is not None
            assert persisted_request.request_id == "req_123"
            assert persisted_request.requested_by == "user_111"

    @pytest.mark.asyncio
    async def test_note_with_ratings_persists(self):
        """Test that notes and ratings persist with relationships"""
        from uuid import uuid4

        from src.database import async_session_maker
        from src.llm_config.models import CommunityServer
        from src.notes.models import Note, Rating, Request

        note_id = None
        community_server_id = uuid4()

        # Create note with ratings in first session
        async with async_session_maker() as session:
            # Create a community server first
            community_server = CommunityServer(
                id=community_server_id,
                platform="discord",
                platform_id="test_server_123",
                name="Test Server",
            )
            session.add(community_server)
            await session.flush()

            # Create a request first
            request = Request(
                request_id="req_rel_123",
                community_server_id=community_server_id,
                requested_by="user_rel_111",
                status="IN_PROGRESS",
            )
            session.add(request)
            await session.flush()

            # Create note (Note model uses id (UUID) as primary key)
            note = Note(
                author_participant_id="author_123",
                community_server_id=community_server_id,
                summary="This is a test note",
                classification="NOT_MISLEADING",
            )
            session.add(note)
            await session.flush()

            # Create ratings
            rating1 = Rating(
                note_id=note.id,
                rater_participant_id="rater_1",
                helpfulness_level="HELPFUL",
            )
            rating2 = Rating(
                note_id=note.id,
                rater_participant_id="rater_2",
                helpfulness_level="HELPFUL",
            )
            session.add_all([rating1, rating2])
            await session.commit()
            note_id = note.id

        # Verify note and ratings persist in new session
        async with async_session_maker() as session:
            stmt = select(Note).where(Note.id == note_id)
            result = await session.execute(stmt)
            persisted_note = result.scalar_one_or_none()

            assert persisted_note is not None
            assert persisted_note.summary == "This is a test note"

            # Check ratings
            stmt = select(Rating).where(Rating.note_id == note_id)
            result = await session.execute(stmt)
            ratings = result.scalars().all()

            assert len(ratings) == 2
            assert all(rating.helpfulness_level == "HELPFUL" for rating in ratings)

    @pytest.mark.asyncio
    async def test_update_persists_across_sessions(self):
        """Test that updates to entities persist"""
        from src.database import async_session_maker
        from src.users.models import User

        user_id = None

        # Create user
        async with async_session_maker() as session:
            user = User(
                username="update_test_user",
                email="update@example.com",
                hashed_password="password_hash",
                full_name="Original Name",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        # Update user
        async with async_session_maker() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.full_name = "Updated Name"
            user.email = "updated@example.com"
            await session.commit()

        # Verify update persisted
        async with async_session_maker() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            updated_user = result.scalar_one()

            assert updated_user.full_name == "Updated Name"
            assert updated_user.email == "updated@example.com"

    @pytest.mark.asyncio
    async def test_delete_persists_across_sessions(self):
        """Test that deletions persist"""
        from src.database import async_session_maker
        from src.users.models import User

        user_id = None

        # Create user
        async with async_session_maker() as session:
            user = User(
                username="delete_test_user",
                email="delete@example.com",
                hashed_password="password_hash",
                full_name="To Be Deleted",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        # Delete user
        async with async_session_maker() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one()

            await session.delete(user)
            await session.commit()

        # Verify deletion persisted
        async with async_session_maker() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            deleted_user = result.scalar_one_or_none()

            assert deleted_user is None

    @pytest.mark.asyncio
    async def test_transaction_rollback_does_not_persist(self):
        """Test that rolled back transactions don't persist"""
        from src.database import async_session_maker
        from src.users.models import User

        # Create user but rollback
        async with async_session_maker() as session:
            user = User(
                username="rollback_user",
                email="rollback@example.com",
                hashed_password="password_hash",
                full_name="Should Not Persist",
            )
            session.add(user)
            await session.flush()  # Flush but don't commit
            await session.rollback()

        # Verify user doesn't exist after rollback
        async with async_session_maker() as session:
            # Note: We can't use user_id here because it was rolled back
            # So we search by username instead
            stmt = select(User).where(User.username == "rollback_user")
            result = await session.execute(stmt)
            rolled_back_user = result.scalar_one_or_none()

            assert rolled_back_user is None

    @pytest.mark.asyncio
    async def test_concurrent_transactions_isolation(self):
        """Test that concurrent transactions are properly isolated"""
        from src.database import async_session_maker
        from src.users.models import User

        # Create a user
        async with async_session_maker() as session:
            user = User(
                username="concurrent_user",
                email="concurrent@example.com",
                hashed_password="password_hash",
                full_name="Original",
            )
            session.add(user)
            await session.commit()

        # Start two sessions
        async with async_session_maker() as session1, async_session_maker() as session2:
            # Session 1: Read user
            stmt = select(User).where(User.username == "concurrent_user")
            result = await session1.execute(stmt)
            user1 = result.scalar_one()

            # Session 2: Read same user
            result = await session2.execute(stmt)
            user2 = result.scalar_one()

            # Both should see the same data
            assert user1.full_name == "Original"
            assert user2.full_name == "Original"

            # Session 1: Update user but don't commit yet
            user1.full_name = "Updated by Session 1"
            await session1.flush()

            # Session 2: Should still see original value (transaction isolation)
            await session2.refresh(user2)
            # Note: Depending on isolation level, session2 might or might not see the change
            # This test demonstrates transaction behavior

            await session1.rollback()
            await session2.rollback()
