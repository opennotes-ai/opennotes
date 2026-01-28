"""
Unit tests for resource ownership verification dependencies.

These tests use mocked database operations to test the ownership logic
without requiring Docker or an actual database connection.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.auth.ownership_dependencies import (
    _is_owner_by_participant,
    _is_owner_by_profile,
    verify_note_ownership,
    verify_rating_ownership,
    verify_request_ownership,
)
from src.notes.models import Note, Rating
from src.notes.models import Request as NoteRequest
from src.users.models import User


def create_mock_user(
    user_id: int = 1,
    username: str = "testuser",
    email: str = "test@example.com",
    discord_id: str | None = None,
    is_service_account: bool = False,
) -> User:
    """Create a mock User object."""
    if is_service_account:
        email = f"{username}@opennotes.local"
        username = f"{username}-service"

    user = User(
        id=user_id,
        username=username,
        email=email,
        hashed_password="unused",
        role="user",
    )
    user.discord_id = discord_id
    return user


def create_mock_note(
    note_id=None,
    author_id=None,
    community_server_id=None,
) -> Note:
    """Create a mock Note object."""
    note = MagicMock(spec=Note)
    note.id = note_id or uuid4()
    note.author_id = author_id or uuid4()
    note.community_server_id = community_server_id or uuid4()
    note.ratings = []
    note.request = None
    return note


def create_mock_rating(
    rating_id=None,
    rater_id=None,
    note=None,
) -> Rating:
    """Create a mock Rating object."""
    rating = MagicMock(spec=Rating)
    rating.id = rating_id or uuid4()
    rating.rater_id = rater_id or uuid4()
    rating.note = note or create_mock_note()
    return rating


_UNSET = object()


def create_mock_request(
    request_id: str = "req-123",
    requested_by: str = "discord-user-789",
    community_server_id=_UNSET,
) -> NoteRequest:
    """Create a mock NoteRequest object."""
    req = MagicMock(spec=NoteRequest)
    req.id = uuid4()
    req.request_id = request_id
    req.requested_by = requested_by
    req.community_server_id = uuid4() if community_server_id is _UNSET else community_server_id
    req.message_archive = None
    return req


@pytest.mark.unit
class TestOwnershipHelpers:
    """Unit tests for ownership helper functions."""

    def test_is_owner_by_profile_match(self):
        """Matching profile IDs should return True."""
        profile_id = uuid4()
        assert _is_owner_by_profile(profile_id, profile_id) is True

    def test_is_owner_by_profile_no_match(self):
        """Non-matching profile IDs should return False."""
        assert _is_owner_by_profile(uuid4(), uuid4()) is False

    def test_is_owner_by_profile_none_resource(self):
        """None resource profile_id should return False."""
        assert _is_owner_by_profile(None, uuid4()) is False

    def test_is_owner_by_profile_none_user(self):
        """None user profile_id should return False."""
        assert _is_owner_by_profile(uuid4(), None) is False

    def test_is_owner_by_profile_both_none(self):
        """Both None should return False."""
        assert _is_owner_by_profile(None, None) is False

    def test_is_owner_by_participant_match(self):
        """Matching participant IDs should return True."""
        discord_id = "discord-123"
        assert _is_owner_by_participant(discord_id, discord_id) is True

    def test_is_owner_by_participant_no_match(self):
        """Non-matching participant IDs should return False."""
        assert _is_owner_by_participant("discord-123", "discord-456") is False

    def test_is_owner_by_participant_none_resource(self):
        """None resource participant_id should return False."""
        assert _is_owner_by_participant(None, "discord-123") is False

    def test_is_owner_by_participant_none_user(self):
        """None user discord_id should return False."""
        assert _is_owner_by_participant("discord-123", None) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyNoteOwnership:
    """Unit tests for verify_note_ownership dependency."""

    async def test_owner_by_profile_id_returns_note(self):
        """Owner by author_id (user profile ID) should get access to note."""
        note_id = uuid4()
        author_id = uuid4()
        community_id = uuid4()
        note = create_mock_note(
            note_id=note_id,
            author_id=author_id,
            community_server_id=community_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = note
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=author_id,
            ),
            # Also patch in community_dependencies since verify_community_admin_by_uuid
            # calls _get_profile_id_from_user using its own module reference
            patch(
                "src.auth.community_dependencies._get_profile_id_from_user",
                return_value=author_id,
            ),
        ):
            result = await verify_note_ownership(note_id, user, mock_db, mock_request)

            assert result == note

    async def test_service_account_always_has_access(self):
        """Service accounts should always have access to notes."""
        note_id = uuid4()
        note = create_mock_note(note_id=note_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = note
        mock_db.execute.return_value = mock_result

        user = create_mock_user(is_service_account=True)
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("src.auth.ownership_dependencies.is_service_account", return_value=True):
            result = await verify_note_ownership(note_id, user, mock_db, mock_request)

            assert result == note

    async def test_note_not_found_returns_404(self):
        """Non-existent note should return 404."""
        note_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_note_ownership(note_id, user, mock_db, mock_request)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    async def test_non_owner_gets_403(self):
        """Non-owner should get 403 Forbidden."""
        note_id = uuid4()
        note = create_mock_note(
            note_id=note_id,
            author_id=uuid4(),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = note
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        async def admin_check_fails(*args, **kwargs):
            raise HTTPException(status_code=403, detail="Not admin")

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=uuid4(),
            ),
            patch(
                "src.auth.ownership_dependencies.verify_community_admin_by_uuid",
                side_effect=admin_check_fails,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_note_ownership(note_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "permission" in exc_info.value.detail.lower()

    async def test_community_admin_can_access_any_note(self):
        """Community admin should have access to any note in their community."""
        note_id = uuid4()
        community_id = uuid4()
        note = create_mock_note(
            note_id=note_id,
            author_id=uuid4(),
            community_server_id=community_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = note
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-admin")
        mock_request = MagicMock()
        mock_request.headers = {}

        admin_membership = MagicMock()
        admin_membership.role = "admin"

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=uuid4(),
            ),
            patch(
                "src.auth.ownership_dependencies.verify_community_admin_by_uuid",
                return_value=admin_membership,
            ),
        ):
            result = await verify_note_ownership(note_id, user, mock_db, mock_request)

            assert result == note


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyRatingOwnership:
    """Unit tests for verify_rating_ownership dependency."""

    async def test_owner_by_profile_id_returns_rating(self):
        """Owner by profile_id should get access to rating."""
        rating_id = uuid4()
        profile_id = uuid4()
        rating = create_mock_rating(
            rating_id=rating_id,
            rater_id=profile_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rating
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=profile_id,
            ),
        ):
            result = await verify_rating_ownership(rating_id, user, mock_db, mock_request)

            assert result == rating

    async def test_owner_by_rater_id_returns_rating(self):
        """Owner by rater_id (user profile ID) should get access to rating."""
        rating_id = uuid4()
        rater_id = uuid4()
        rating = create_mock_rating(
            rating_id=rating_id,
            rater_id=rater_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rating
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-user")
        mock_request = MagicMock()
        mock_request.headers = {}

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=rater_id,
            ),
        ):
            result = await verify_rating_ownership(rating_id, user, mock_db, mock_request)

            assert result == rating

    async def test_rating_not_found_returns_404(self):
        """Non-existent rating should return 404."""
        rating_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_rating_ownership(rating_id, user, mock_db, mock_request)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    async def test_non_owner_gets_403(self):
        """Non-owner should get 403 Forbidden."""
        rating_id = uuid4()
        rating = create_mock_rating(
            rating_id=rating_id,
            rater_id=uuid4(),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rating
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        async def admin_check_fails(*args, **kwargs):
            raise HTTPException(status_code=403, detail="Not admin")

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies._get_profile_id_from_user",
                return_value=uuid4(),
            ),
            patch(
                "src.auth.ownership_dependencies.verify_community_admin_by_uuid",
                side_effect=admin_check_fails,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_rating_ownership(rating_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "permission" in exc_info.value.detail.lower()

    async def test_service_account_always_has_access(self):
        """Service accounts should always have access to ratings."""
        rating_id = uuid4()
        rating = create_mock_rating(rating_id=rating_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rating
        mock_db.execute.return_value = mock_result

        user = create_mock_user(is_service_account=True)
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("src.auth.ownership_dependencies.is_service_account", return_value=True):
            result = await verify_rating_ownership(rating_id, user, mock_db, mock_request)

            assert result == rating


@pytest.mark.unit
@pytest.mark.asyncio
class TestVerifyRequestOwnership:
    """Unit tests for verify_request_ownership dependency."""

    async def test_owner_by_participant_id_returns_request(self):
        """Owner by requested_by (legacy) should get access to request."""
        request_id = "req-123"
        discord_id = "discord-requester-123"
        req = create_mock_request(
            request_id=request_id,
            requested_by=discord_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id=discord_id)
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("src.auth.ownership_dependencies.is_service_account", return_value=False):
            result = await verify_request_ownership(request_id, user, mock_db, mock_request)

            assert result == req

    async def test_request_not_found_returns_404(self):
        """Non-existent request should return 404."""
        request_id = "req-nonexistent"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user = create_mock_user()
        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_request_ownership(request_id, user, mock_db, mock_request)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    async def test_non_owner_gets_403(self):
        """Non-owner should get 403 Forbidden."""
        request_id = "req-123"
        req = create_mock_request(
            request_id=request_id,
            requested_by="discord-other",
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        async def admin_check_fails(*args, **kwargs):
            raise HTTPException(status_code=403, detail="Not admin")

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies.verify_community_admin_by_uuid",
                side_effect=admin_check_fails,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_request_ownership(request_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "permission" in exc_info.value.detail.lower()

    async def test_service_account_always_has_access(self):
        """Service accounts should always have access to requests."""
        request_id = "req-123"
        req = create_mock_request(request_id=request_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        mock_db.execute.return_value = mock_result

        user = create_mock_user(is_service_account=True)
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("src.auth.ownership_dependencies.is_service_account", return_value=True):
            result = await verify_request_ownership(request_id, user, mock_db, mock_request)

            assert result == req

    async def test_request_without_community_non_owner_gets_403(self):
        """Request without community_server_id should still return 403 for non-owner."""
        request_id = "req-123"
        req = create_mock_request(
            request_id=request_id,
            requested_by="discord-other",
            community_server_id=None,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-different")
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch("src.auth.ownership_dependencies.is_service_account", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await verify_request_ownership(request_id, user, mock_db, mock_request)

            assert exc_info.value.status_code == 403
            assert "permission" in exc_info.value.detail.lower()

    async def test_community_admin_can_access_any_request(self):
        """Community admin should have access to any request in their community."""
        request_id = "req-123"
        community_id = uuid4()
        req = create_mock_request(
            request_id=request_id,
            requested_by="discord-other",
            community_server_id=community_id,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        mock_db.execute.return_value = mock_result

        user = create_mock_user(discord_id="discord-admin")
        mock_request = MagicMock()
        mock_request.headers = {}

        admin_membership = MagicMock()
        admin_membership.role = "admin"

        with (
            patch("src.auth.ownership_dependencies.is_service_account", return_value=False),
            patch(
                "src.auth.ownership_dependencies.verify_community_admin_by_uuid",
                return_value=admin_membership,
            ),
        ):
            result = await verify_request_ownership(request_id, user, mock_db, mock_request)

            assert result == req
