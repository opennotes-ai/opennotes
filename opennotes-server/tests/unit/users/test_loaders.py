"""Tests for user loaders module.

This module tests the composable SQLAlchemy loader option functions
for UserProfile, CommunityMember, and UserIdentity relationships.
"""

from sqlalchemy import select

from src.users.profile_models import CommunityMember, UserIdentity, UserProfile


class TestProfileLoaders:
    """Tests for UserProfile loader functions."""

    def test_profile_identities_returns_tuple(self) -> None:
        """profile_identities() should return a tuple of loader options."""
        from src.users.loaders import profile_identities

        result = profile_identities()

        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_profile_memberships_returns_tuple(self) -> None:
        """profile_memberships() should return a tuple of loader options."""
        from src.users.loaders import profile_memberships

        result = profile_memberships()

        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_profile_full_composes_identities_and_memberships(self) -> None:
        """profile_full() should compose profile_identities() and profile_memberships()."""
        from src.users.loaders import profile_full, profile_identities, profile_memberships

        full_result = profile_full()
        identities_result = profile_identities()
        memberships_result = profile_memberships()

        assert isinstance(full_result, tuple)
        assert len(full_result) == len(identities_result) + len(memberships_result)

    def test_profile_loaders_can_be_unpacked_into_select_options(self) -> None:
        """Profile loader options should be usable with select().options()."""
        from src.users.loaders import profile_full

        stmt = select(UserProfile).options(*profile_full())

        assert stmt is not None


class TestMemberLoaders:
    """Tests for CommunityMember loader functions."""

    def test_member_profile_returns_tuple(self) -> None:
        """member_profile() should return a tuple of loader options."""
        from src.users.loaders import member_profile

        result = member_profile()

        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_member_inviter_returns_tuple(self) -> None:
        """member_inviter() should return a tuple of loader options."""
        from src.users.loaders import member_inviter

        result = member_inviter()

        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_member_full_composes_profile_and_inviter(self) -> None:
        """member_full() should compose member_profile() and member_inviter()."""
        from src.users.loaders import member_full, member_inviter, member_profile

        full_result = member_full()
        profile_result = member_profile()
        inviter_result = member_inviter()

        assert isinstance(full_result, tuple)
        assert len(full_result) == len(profile_result) + len(inviter_result)

    def test_member_loaders_can_be_unpacked_into_select_options(self) -> None:
        """Member loader options should be usable with select().options()."""
        from src.users.loaders import member_full

        stmt = select(CommunityMember).options(*member_full())

        assert stmt is not None


class TestIdentityLoaders:
    """Tests for UserIdentity loader functions."""

    def test_identity_with_profile_returns_tuple(self) -> None:
        """identity_with_profile() should return a tuple of loader options."""
        from src.users.loaders import identity_with_profile

        result = identity_with_profile()

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_identity_loaders_can_be_unpacked_into_select_options(self) -> None:
        """Identity loader options should be usable with select().options()."""
        from src.users.loaders import identity_with_profile

        stmt = select(UserIdentity).options(*identity_with_profile())

        assert stmt is not None


class TestLoaderComposition:
    """Tests for combining multiple loader functions."""

    def test_can_combine_profile_and_member_loaders(self) -> None:
        """Multiple loader functions can be combined in a single query."""
        from src.users.loaders import profile_full, profile_identities

        stmt = select(UserProfile).options(*profile_identities(), *profile_full())

        assert stmt is not None

    def test_loader_options_are_sqlalchemy_load_objects(self) -> None:
        """All loader functions should return SQLAlchemy Load objects."""
        from sqlalchemy.orm.strategy_options import Load

        from src.users.loaders import (
            identity_with_profile,
            member_full,
            member_inviter,
            member_profile,
            profile_full,
            profile_identities,
            profile_memberships,
        )

        for loader_func in [
            profile_identities,
            profile_memberships,
            profile_full,
            member_profile,
            member_inviter,
            member_full,
        ]:
            result = loader_func()
            for item in result:
                assert isinstance(item, Load), f"{loader_func.__name__} should return Load objects"

        for item in identity_with_profile():
            assert isinstance(item, Load), "identity_with_profile should return Load objects"
