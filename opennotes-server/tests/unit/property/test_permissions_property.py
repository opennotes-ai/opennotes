"""
Property-based tests for permissions hierarchy and authorization logic.

These tests verify structural invariants of the 4-tier permission hierarchy:
1. Service accounts (highest) - always have access regardless of membership
2. OpenNotes admins - cross-community admin access
3. Discord Manage Server / Community admins/moderators
4. Regular members - need active, non-banned membership

Key properties tested:
- Hierarchy transitivity: higher tiers imply lower-tier access
- Service account supremacy: always granted regardless of other state
- Banned member denial: banned_at blocks member access even if is_active=True
- NULL membership denial: non-admin users without membership get no access
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from hypothesis import assume, given
from hypothesis import strategies as st

from src.auth.permissions import (
    has_community_admin_access,
    has_community_member_access,
    is_community_admin,
    is_service_account,
)


@dataclass
class FakeUser:
    principal_type: str | None = "human"
    is_service_account: bool = False
    email: str | None = "user@example.com"
    username: str | None = "testuser"


@dataclass
class FakeUserProfile:
    is_opennotes_admin: bool = False


@dataclass
class FakeCommunityMember:
    role: str = "member"
    is_active: bool = True
    banned_at: datetime | None = None


principal_type_strategy = st.sampled_from(["human", "agent", "system", None])

role_strategy = st.sampled_from(["admin", "moderator", "member", "viewer", "guest"])

banned_at_strategy = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2020, 1, 1),  # noqa: DTZ001
        max_value=datetime(2030, 1, 1),  # noqa: DTZ001
        timezones=st.just(UTC),
    ),
)


def make_sa_user() -> FakeUser:
    return FakeUser(principal_type="agent")


def make_human_user() -> FakeUser:
    return FakeUser(principal_type="human")


class TestIsServiceAccountProperties:
    @given(principal_type=principal_type_strategy)
    def test_service_account_iff_agent_or_system(self, principal_type):
        user = FakeUser(principal_type=principal_type)
        result = is_service_account(user)
        assert result == (principal_type in ("agent", "system"))

    def test_human_principal_type_is_not_service_account(self):
        user = FakeUser(principal_type="human")
        assert not is_service_account(user)

    def test_none_principal_type_is_not_service_account(self):
        user = FakeUser(principal_type=None)
        assert not is_service_account(user)


class TestIsCommunityAdminProperties:
    @given(role=role_strategy)
    def test_admin_and_moderator_are_community_admins(self, role):
        member = FakeCommunityMember(role=role)
        result = is_community_admin(member)
        assert result == (role in ["admin", "moderator"])


class TestHierarchyTransitivityProperties:
    """Property tests verifying that higher-tier access implies lower-tier access.

    The permission hierarchy has an important asymmetry:
    - Tier 1 (service accounts) and Tier 2 (opennotes admins) grant BOTH admin
      and member access unconditionally.
    - Tier 3 (Discord Manage Server) and Tier 4 (community role) grant admin
      access but do NOT automatically grant member access. Member access has
      its own gate: is_active=True AND banned_at=None.

    This means "admin access implies member access" only holds for tiers 1-2.
    """

    @given(
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_service_account_admin_implies_member(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        user = FakeUser(principal_type="agent")
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(membership=membership, profile=profile, user=user)
        assert has_community_member_access(membership=membership, profile=profile, user=user)

    @given(
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_opennotes_admin_admin_implies_member(
        self,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=True)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(membership=membership, profile=profile, user=user)
        assert has_community_member_access(membership=membership, profile=profile, user=user)

    @given(
        role=st.sampled_from(["admin", "moderator"]),
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
    )
    def test_community_admin_role_does_not_imply_member_access(
        self,
        role,
        is_active,
        banned_at,
    ):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)

        admin_access = has_community_admin_access(membership=membership, profile=profile, user=user)
        member_access = has_community_member_access(
            membership=membership, profile=profile, user=user
        )

        assert admin_access, f"Role {role} should always grant admin access"

        expected_member = is_active and banned_at is None
        assert member_access == expected_member, (
            f"Member access for role={role}, is_active={is_active}, banned_at={banned_at} "
            f"should be {expected_member} but got {member_access}"
        )

    @given(
        principal_type=principal_type_strategy,
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_service_account_outranks_opennotes_admin(
        self,
        principal_type,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        user = FakeUser(principal_type=principal_type)
        user_is_sa = is_service_account(user)

        if user_is_sa:
            profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
            membership = (
                FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
                if has_membership
                else None
            )

            assert has_community_admin_access(membership=membership, profile=profile, user=user)
            assert has_community_member_access(membership=membership, profile=profile, user=user)


class TestServiceAccountSupremacyProperties:
    @given(
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
        has_discord_manage_server=st.booleans(),
    )
    def test_agent_principal_always_grants_admin_access(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
        has_discord_manage_server,
    ):
        user = FakeUser(principal_type="agent")
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(
            membership=membership,
            profile=profile,
            user=user,
            has_discord_manage_server=has_discord_manage_server,
        )

    @given(
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
        has_discord_manage_server=st.booleans(),
    )
    def test_system_principal_always_grants_admin_access(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
        has_discord_manage_server,
    ):
        user = FakeUser(principal_type="system")
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(
            membership=membership,
            profile=profile,
            user=user,
            has_discord_manage_server=has_discord_manage_server,
        )

    @given(
        is_on_admin=st.booleans(),
        has_membership=st.booleans(),
        banned_at=banned_at_strategy,
    )
    def test_service_account_always_grants_member_access(
        self,
        is_on_admin,
        has_membership,
        banned_at,
    ):
        user = FakeUser(principal_type="agent")
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(is_active=False, banned_at=banned_at) if has_membership else None
        )

        assert has_community_member_access(membership=membership, profile=profile, user=user)


class TestBannedMemberDenialProperties:
    @given(
        role=role_strategy,
        is_active=st.booleans(),
        ban_time=st.datetimes(
            min_value=datetime(2020, 1, 1),  # noqa: DTZ001
            max_value=datetime(2030, 1, 1),  # noqa: DTZ001
            timezones=st.just(UTC),
        ),
    )
    def test_banned_member_denied_member_access(self, role, is_active, ban_time):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role=role, is_active=is_active, banned_at=ban_time)

        result = has_community_member_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        assert not result, (
            f"Banned member (banned_at={ban_time}, is_active={is_active}, role={role}) "
            f"should be denied member access"
        )

    @given(
        role=role_strategy,
        ban_time=st.datetimes(
            min_value=datetime(2020, 1, 1),  # noqa: DTZ001
            max_value=datetime(2030, 1, 1),  # noqa: DTZ001
            timezones=st.just(UTC),
        ),
    )
    def test_banned_admin_still_has_admin_access_via_role(self, role, ban_time):
        """Community admin access checks role, not ban status.

        The has_community_admin_access function does not check banned_at;
        only has_community_member_access checks it. This verifies that
        admin-role banned members still pass admin check (by design,
        admin access is revoked by changing role, not by banning).
        """
        assume(role in ["admin", "moderator"])
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role=role, is_active=True, banned_at=ban_time)

        result = has_community_admin_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        assert result, (
            f"Admin/moderator role ({role}) should grant admin access "
            f"even when banned (ban enforcement is at member-access level)"
        )


class TestNullMembershipDenialProperties:
    @given(
        has_discord_manage_server=st.booleans(),
    )
    def test_null_membership_no_admin_no_sa_denies_member_access(self, has_discord_manage_server):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)

        result = has_community_member_access(
            membership=None,
            profile=profile,
            user=user,
        )

        assert not result, "NULL membership should deny member access for regular users"

    @given(
        has_discord_manage_server=st.booleans(),
    )
    def test_null_membership_no_admin_no_sa_denies_admin_access(self, has_discord_manage_server):
        assume(not has_discord_manage_server)

        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)

        result = has_community_admin_access(
            membership=None,
            profile=profile,
            user=user,
            has_discord_manage_server=has_discord_manage_server,
        )

        assert not result, "NULL membership should deny admin access for regular users"

    def test_null_membership_with_opennotes_admin_grants_member_access(self):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=True)

        assert has_community_member_access(membership=None, profile=profile, user=user)

    def test_null_membership_with_opennotes_admin_grants_admin_access(self):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=True)

        assert has_community_admin_access(membership=None, profile=profile, user=user)

    def test_null_membership_with_service_account_grants_both(self):
        user = FakeUser(principal_type="agent")
        profile = FakeUserProfile(is_opennotes_admin=False)

        assert has_community_admin_access(membership=None, profile=profile, user=user)
        assert has_community_member_access(membership=None, profile=profile, user=user)


class TestInactiveMemberProperties:
    @given(role=role_strategy)
    def test_inactive_non_banned_member_denied_member_access(self, role):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role=role, is_active=False, banned_at=None)

        result = has_community_member_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        assert not result, f"Inactive member (role={role}) should be denied member access"


class TestNoneArgumentProperties:
    @given(
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
    )
    def test_none_user_none_profile_falls_through_to_membership(self, role, is_active, banned_at):
        membership = FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)

        admin_result = has_community_admin_access(
            membership=membership,
            profile=None,
            user=None,
        )
        assert admin_result == (role in ["admin", "moderator"])

        member_result = has_community_member_access(
            membership=membership,
            profile=None,
            user=None,
        )
        assert member_result == (is_active and banned_at is None)

    def test_all_none_denies_everything(self):
        assert not has_community_admin_access(membership=None, profile=None, user=None)
        assert not has_community_member_access(membership=None, profile=None, user=None)


class TestDiscordManageServerProperties:
    @given(
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_discord_manage_server_grants_admin_without_membership(
        self, role, is_active, banned_at, has_membership
    ):
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        result = has_community_admin_access(
            membership=membership,
            profile=profile,
            user=user,
            has_discord_manage_server=True,
        )

        assert result, "Discord Manage Server should always grant admin access"

    @given(
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
    )
    def test_discord_manage_server_does_not_grant_member_access(self, is_active, banned_at):
        """Discord Manage Server is NOT checked in member access (separate code path).

        has_community_member_access does not accept has_discord_manage_server.
        A user with Manage Server but no active membership is denied member access
        (unless they are also a service account or opennotes admin).
        """
        user = FakeUser(principal_type="human")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role="member", is_active=is_active, banned_at=banned_at)

        result = has_community_member_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        expected = is_active and banned_at is None
        assert result == expected
