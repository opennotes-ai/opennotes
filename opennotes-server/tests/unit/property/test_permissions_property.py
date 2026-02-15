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


service_account_flags = st.fixed_dictionaries(
    {
        "is_service_account": st.booleans(),
        "email_is_service": st.booleans(),
        "username_is_service": st.booleans(),
    }
)


def make_user(
    is_sa: bool = False,
    email_is_service: bool = False,
    username_is_service: bool = False,
) -> FakeUser:
    return FakeUser(
        is_service_account=is_sa,
        email="bot@opennotes.local" if email_is_service else "user@example.com",
        username="deploy-service" if username_is_service else "regularuser",
    )


role_strategy = st.sampled_from(["admin", "moderator", "member", "viewer", "guest"])

banned_at_strategy = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2020, 1, 1, tzinfo=UTC),
        max_value=datetime(2030, 1, 1, tzinfo=UTC),
    ).map(lambda dt: dt.replace(tzinfo=UTC)),
)


class TestIsServiceAccountProperties:
    """Property tests for is_service_account detection."""

    @given(sa_flags=service_account_flags)
    def test_any_service_indicator_grants_service_status(self, sa_flags):
        """If ANY of the 3 indicators is True, user is a service account."""
        user = make_user(
            is_sa=sa_flags["is_service_account"],
            email_is_service=sa_flags["email_is_service"],
            username_is_service=sa_flags["username_is_service"],
        )

        result = is_service_account(user)

        any_flag_set = (
            sa_flags["is_service_account"]
            or sa_flags["email_is_service"]
            or sa_flags["username_is_service"]
        )
        assert result == any_flag_set

    @given(sa_flags=service_account_flags)
    def test_no_service_indicator_denies_service_status(self, sa_flags):
        """If NONE of the 3 indicators is True, user is NOT a service account."""
        assume(
            not sa_flags["is_service_account"]
            and not sa_flags["email_is_service"]
            and not sa_flags["username_is_service"]
        )

        user = make_user(
            is_sa=False,
            email_is_service=False,
            username_is_service=False,
        )

        assert not is_service_account(user)


class TestIsCommunityAdminProperties:
    """Property tests for community admin role detection."""

    @given(role=role_strategy)
    def test_admin_and_moderator_are_community_admins(self, role):
        """Only 'admin' and 'moderator' roles grant community admin status."""
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
        """Service accounts (tier 1) always have both admin and member access."""
        user = FakeUser(is_service_account=True, email="regular@example.com", username="regular")
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
        """OpenNotes admins (tier 2) always have both admin and member access."""
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
        """Community admin/moderator role grants admin access but member access
        depends on is_active and banned_at independently.

        This documents a design choice: admin and member access are checked
        with different criteria at the community membership level.
        """
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
        is_sa=st.booleans(),
        email_is_service=st.booleans(),
        username_is_service=st.booleans(),
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_service_account_outranks_opennotes_admin(
        self,
        is_sa,
        email_is_service,
        username_is_service,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        """Service account access is independent of opennotes_admin status."""
        user = make_user(
            is_sa=is_sa, email_is_service=email_is_service, username_is_service=username_is_service
        )
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
    """Property tests verifying service accounts always have access."""

    @given(
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
        has_discord_manage_server=st.booleans(),
    )
    def test_service_account_flag_always_grants_admin_access(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
        has_discord_manage_server,
    ):
        """Service account (via flag) always gets admin access regardless of other state."""
        user = FakeUser(is_service_account=True, email="regular@example.com", username="regular")
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
    )
    def test_service_account_email_always_grants_admin_access(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        """Service account (via email) always gets admin access regardless of other state."""
        user = FakeUser(
            is_service_account=False, email="worker@opennotes.local", username="regular"
        )
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(membership=membership, profile=profile, user=user)

    @given(
        is_on_admin=st.booleans(),
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_service_account_username_always_grants_admin_access(
        self,
        is_on_admin,
        role,
        is_active,
        banned_at,
        has_membership,
    ):
        """Service account (via username) always gets admin access regardless of other state."""
        user = FakeUser(
            is_service_account=False, email="regular@example.com", username="deploy-service"
        )
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(role=role, is_active=is_active, banned_at=banned_at)
            if has_membership
            else None
        )

        assert has_community_admin_access(membership=membership, profile=profile, user=user)

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
        """Service accounts get member access even without membership or when banned."""
        user = FakeUser(is_service_account=True)
        profile = FakeUserProfile(is_opennotes_admin=is_on_admin)
        membership = (
            FakeCommunityMember(is_active=False, banned_at=banned_at) if has_membership else None
        )

        assert has_community_member_access(membership=membership, profile=profile, user=user)


class TestBannedMemberDenialProperties:
    """Property tests verifying banned members are denied member access."""

    @given(
        role=role_strategy,
        is_active=st.booleans(),
        ban_time=st.datetimes(
            min_value=datetime(2020, 1, 1, tzinfo=UTC),
            max_value=datetime(2030, 1, 1, tzinfo=UTC),
        ).map(lambda dt: dt.replace(tzinfo=UTC)),
    )
    def test_banned_member_denied_member_access(self, role, is_active, ban_time):
        """A member with banned_at set is denied member access, even if is_active=True."""
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
            min_value=datetime(2020, 1, 1, tzinfo=UTC),
            max_value=datetime(2030, 1, 1, tzinfo=UTC),
        ).map(lambda dt: dt.replace(tzinfo=UTC)),
    )
    def test_banned_admin_still_has_admin_access_via_role(self, role, ban_time):
        """Community admin access checks role, not ban status.

        The has_community_admin_access function does not check banned_at;
        only has_community_member_access checks it. This verifies that
        admin-role banned members still pass admin check (by design,
        admin access is revoked by changing role, not by banning).
        """
        assume(role in ["admin", "moderator"])
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
    """Property tests verifying NULL membership blocks non-admin users."""

    @given(
        has_discord_manage_server=st.booleans(),
    )
    def test_null_membership_no_admin_no_sa_denies_member_access(self, has_discord_manage_server):
        """Regular users without membership are denied member access."""
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
        """Regular users without membership and without Discord perms get no admin access."""
        assume(not has_discord_manage_server)

        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
        profile = FakeUserProfile(is_opennotes_admin=False)

        result = has_community_admin_access(
            membership=None,
            profile=profile,
            user=user,
            has_discord_manage_server=has_discord_manage_server,
        )

        assert not result, "NULL membership should deny admin access for regular users"

    def test_null_membership_with_opennotes_admin_grants_member_access(self):
        """OpenNotes admins get member access even without membership."""
        user = FakeUser(is_service_account=False, email="admin@example.com", username="onadmin")
        profile = FakeUserProfile(is_opennotes_admin=True)

        assert has_community_member_access(membership=None, profile=profile, user=user)

    def test_null_membership_with_opennotes_admin_grants_admin_access(self):
        """OpenNotes admins get admin access even without membership."""
        user = FakeUser(is_service_account=False, email="admin@example.com", username="onadmin")
        profile = FakeUserProfile(is_opennotes_admin=True)

        assert has_community_admin_access(membership=None, profile=profile, user=user)

    def test_null_membership_with_service_account_grants_both(self):
        """Service accounts get both admin and member access without membership."""
        user = FakeUser(is_service_account=True)
        profile = FakeUserProfile(is_opennotes_admin=False)

        assert has_community_admin_access(membership=None, profile=profile, user=user)
        assert has_community_member_access(membership=None, profile=profile, user=user)


class TestInactiveMemberProperties:
    """Property tests for inactive (is_active=False) membership."""

    @given(role=role_strategy)
    def test_inactive_non_banned_member_denied_member_access(self, role):
        """Inactive members (is_active=False, no ban) are denied member access."""
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role=role, is_active=False, banned_at=None)

        result = has_community_member_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        assert not result, f"Inactive member (role={role}) should be denied member access"


class TestNoneArgumentProperties:
    """Property tests for None user/profile arguments."""

    @given(
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
    )
    def test_none_user_none_profile_falls_through_to_membership(self, role, is_active, banned_at):
        """With user=None and profile=None, only membership state matters."""
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
        """With all None arguments, both admin and member access are denied."""
        assert not has_community_admin_access(membership=None, profile=None, user=None)
        assert not has_community_member_access(membership=None, profile=None, user=None)


class TestDiscordManageServerProperties:
    """Property tests for Discord Manage Server permission interactions."""

    @given(
        role=role_strategy,
        is_active=st.booleans(),
        banned_at=banned_at_strategy,
        has_membership=st.booleans(),
    )
    def test_discord_manage_server_grants_admin_without_membership(
        self, role, is_active, banned_at, has_membership
    ):
        """Discord Manage Server permission grants admin access regardless of membership."""
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
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
        user = FakeUser(is_service_account=False, email="user@example.com", username="regular")
        profile = FakeUserProfile(is_opennotes_admin=False)
        membership = FakeCommunityMember(role="member", is_active=is_active, banned_at=banned_at)

        result = has_community_member_access(
            membership=membership,
            profile=profile,
            user=user,
        )

        expected = is_active and banned_at is None
        assert result == expected
