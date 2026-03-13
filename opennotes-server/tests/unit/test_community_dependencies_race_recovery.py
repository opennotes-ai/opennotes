from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.users.models import User
from src.users.profile_models import CommunityMember, UserProfile


def _make_integrity_error(constraint_name: str) -> IntegrityError:
    orig = MagicMock()
    orig.diag = MagicMock()
    orig.diag.constraint_name = constraint_name
    return IntegrityError("duplicate key", params=None, orig=orig)


class _AsyncpgUniqueViolation:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name

    def __str__(self) -> str:
        return "duplicate key value violates unique constraint"


def _make_asyncpg_integrity_error(constraint_name: str) -> IntegrityError:
    return IntegrityError(
        "duplicate key",
        params=None,
        orig=_AsyncpgUniqueViolation(constraint_name),
    )


def _make_savepoint() -> MagicMock:
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock(return_value=savepoint)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    return savepoint


def _make_profile(profile_id):
    profile = MagicMock(spec=UserProfile)
    profile.id = profile_id
    profile.is_human = True
    return profile


def _make_membership(community_id, profile_id):
    membership = MagicMock(spec=CommunityMember)
    membership.id = uuid4()
    membership.community_id = community_id
    membership.profile_id = profile_id
    membership.is_active = True
    membership.banned_at = None
    return membership


@pytest.mark.unit
@pytest.mark.asyncio
class TestCommunityDependencyRaceRecovery:
    async def test_duplicate_membership_create_recovers_existing_row(self):
        from src.auth.community_dependencies import _ensure_membership_with_permissions

        community_id = uuid4()
        profile_id = uuid4()
        community = MagicMock()
        community.id = community_id
        profile = _make_profile(profile_id)
        recovered_membership = _make_membership(community_id, profile_id)
        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())

        get_member = AsyncMock(side_effect=[None, recovered_membership])
        create_member = AsyncMock(
            side_effect=_make_integrity_error("idx_community_members_community_profile")
        )

        with (
            patch("src.auth.community_dependencies.get_community_member", new=get_member),
            patch("src.auth.community_dependencies.create_community_member", new=create_member),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            membership = await _ensure_membership_with_permissions(
                community=community,
                profile=profile,
                has_discord_manage_server=True,
                db=mock_db,
            )

        assert membership is recovered_membership
        mock_db.begin_nested.assert_called_once()
        assert get_member.await_count == 2
        logger.info.assert_called_once()

    async def test_asyncpg_duplicate_membership_create_recovers_existing_row(self):
        from src.auth.community_dependencies import _ensure_membership_with_permissions

        community_id = uuid4()
        profile_id = uuid4()
        community = MagicMock()
        community.id = community_id
        profile = _make_profile(profile_id)
        recovered_membership = _make_membership(community_id, profile_id)
        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())

        get_member = AsyncMock(side_effect=[None, recovered_membership])
        create_member = AsyncMock(
            side_effect=_make_asyncpg_integrity_error("idx_community_members_community_profile")
        )

        with (
            patch("src.auth.community_dependencies.get_community_member", new=get_member),
            patch("src.auth.community_dependencies.create_community_member", new=create_member),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            membership = await _ensure_membership_with_permissions(
                community=community,
                profile=profile,
                has_discord_manage_server=True,
                db=mock_db,
            )

        assert membership is recovered_membership
        mock_db.begin_nested.assert_called_once()
        assert get_member.await_count == 2
        logger.info.assert_called_once()

    async def test_duplicate_service_account_profile_create_recovers_existing_identity(self):
        from src.auth.community_dependencies import get_profile_id_from_user

        recovered_profile_id = uuid4()
        identity = MagicMock()
        identity.profile_id = recovered_profile_id
        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())
        user = User(
            id=1,
            username="discord-bot-service",
            email="discord-bot@opennotes.local",
            hashed_password="unused",
            role="admin",
        )

        get_identity = AsyncMock(side_effect=[None, identity])
        create_profile = AsyncMock(
            side_effect=_make_integrity_error("idx_user_identities_provider_user")
        )

        with (
            patch("src.auth.community_dependencies.get_identity_by_provider", new=get_identity),
            patch(
                "src.auth.community_dependencies.create_profile_with_identity", new=create_profile
            ),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            profile_id = await get_profile_id_from_user(mock_db, user)

        assert profile_id == recovered_profile_id
        mock_db.begin_nested.assert_called_once()
        assert get_identity.await_count == 2
        logger.info.assert_called_once()

    async def test_asyncpg_duplicate_service_account_profile_create_recovers_existing_identity(
        self,
    ):
        from src.auth.community_dependencies import get_profile_id_from_user

        recovered_profile_id = uuid4()
        identity = MagicMock()
        identity.profile_id = recovered_profile_id
        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())
        user = User(
            id=1,
            username="discord-bot-service",
            email="discord-bot@opennotes.local",
            hashed_password="unused",
            role="admin",
        )

        get_identity = AsyncMock(side_effect=[None, identity])
        create_profile = AsyncMock(
            side_effect=_make_asyncpg_integrity_error("idx_user_identities_provider_user")
        )

        with (
            patch("src.auth.community_dependencies.get_identity_by_provider", new=get_identity),
            patch(
                "src.auth.community_dependencies.create_profile_with_identity", new=create_profile
            ),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            profile_id = await get_profile_id_from_user(mock_db, user)

        assert profile_id == recovered_profile_id
        mock_db.begin_nested.assert_called_once()
        assert get_identity.await_count == 2
        logger.info.assert_called_once()

    async def test_unexpected_service_account_profile_integrity_error_is_reraised(self):
        from src.auth.community_dependencies import get_profile_id_from_user

        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())
        user = User(
            id=1,
            username="discord-bot-service",
            email="discord-bot@opennotes.local",
            hashed_password="unused",
            role="admin",
        )

        get_identity = AsyncMock(return_value=None)
        unexpected_error = _make_integrity_error("some_other_constraint")
        create_profile = AsyncMock(side_effect=unexpected_error)

        with (
            patch("src.auth.community_dependencies.get_identity_by_provider", new=get_identity),
            patch(
                "src.auth.community_dependencies.create_profile_with_identity", new=create_profile
            ),
            pytest.raises(IntegrityError),
        ):
            await get_profile_id_from_user(mock_db, user)

    async def test_unexpected_membership_integrity_error_is_reraised(self):
        from src.auth.community_dependencies import _ensure_membership_with_permissions

        community = MagicMock()
        community.id = uuid4()
        profile = _make_profile(uuid4())
        mock_db = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())

        get_member = AsyncMock(return_value=None)
        unexpected_error = _make_integrity_error("some_other_constraint")
        create_member = AsyncMock(side_effect=unexpected_error)

        with (
            patch("src.auth.community_dependencies.get_community_member", new=get_member),
            patch("src.auth.community_dependencies.create_community_member", new=create_member),
            pytest.raises(IntegrityError),
        ):
            await _ensure_membership_with_permissions(
                community=community,
                profile=profile,
                has_discord_manage_server=True,
                db=mock_db,
            )

    async def test_duplicate_community_server_create_recovers_existing_row(self):
        from src.auth.community_dependencies import get_community_server_by_platform_id

        existing_server = MagicMock()
        existing_server.id = uuid4()
        existing_server.platform = "discord"
        existing_server.platform_community_server_id = "guild-123"
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())
        mock_db.flush = AsyncMock(
            side_effect=_make_integrity_error("idx_community_servers_platform_community_server_id")
        )

        missing_result = MagicMock()
        missing_result.scalar_one_or_none.return_value = None
        found_result = MagicMock()
        found_result.scalar_one_or_none.return_value = existing_server
        mock_db.execute = AsyncMock(side_effect=[missing_result, found_result])

        with (
            patch(
                "src.auth.community_dependencies._check_circular_reference",
                new=AsyncMock(return_value=None),
            ),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            result = await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id="guild-123",
                auto_create=True,
            )

        assert result is existing_server
        mock_db.begin_nested.assert_called_once()
        mock_db.add.assert_called_once()
        logger.info.assert_called_once()

    async def test_asyncpg_duplicate_community_server_create_recovers_existing_row(self):
        from src.auth.community_dependencies import get_community_server_by_platform_id

        existing_server = MagicMock()
        existing_server.id = uuid4()
        existing_server.platform = "discord"
        existing_server.platform_community_server_id = "guild-123"
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.begin_nested = MagicMock(return_value=_make_savepoint())
        mock_db.flush = AsyncMock(
            side_effect=_make_asyncpg_integrity_error(
                "idx_community_servers_platform_community_server_id"
            )
        )

        missing_result = MagicMock()
        missing_result.scalar_one_or_none.return_value = None
        found_result = MagicMock()
        found_result.scalar_one_or_none.return_value = existing_server
        mock_db.execute = AsyncMock(side_effect=[missing_result, found_result])

        with (
            patch(
                "src.auth.community_dependencies._check_circular_reference",
                new=AsyncMock(return_value=None),
            ),
            patch("src.auth.community_dependencies.logger") as logger,
        ):
            result = await get_community_server_by_platform_id(
                db=mock_db,
                community_server_id="guild-123",
                auto_create=True,
            )

        assert result is existing_server
        mock_db.begin_nested.assert_called_once()
        mock_db.add.assert_called_once()
        logger.info.assert_called_once()
