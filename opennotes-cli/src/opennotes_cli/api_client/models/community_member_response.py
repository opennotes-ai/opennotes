from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..models.community_role import CommunityRole
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_member_response_permissions_type_0 import (
        CommunityMemberResponsePermissionsType0,
    )
    from ..models.user_profile_response import UserProfileResponse


T = TypeVar("T", bound="CommunityMemberResponse")


@_attrs_define
class CommunityMemberResponse:
    """API response schema for community membership with nested profile.

    Attributes:
        created_at (datetime.datetime):
        community_id (UUID): Community identifier
        id (UUID): Unique membership identifier
        profile_id (UUID): User profile identifier
        joined_at (datetime.datetime): When the user joined
        updated_at (datetime.datetime | None | Unset):
        is_external (bool | Unset): True for external participants, False for internal members Default: False.
        role (CommunityRole | Unset): Community membership roles.
        permissions (CommunityMemberResponsePermissionsType0 | None | Unset): Role-specific permissions (JSON object).
            Kept as dict[str, Any] - permission structures vary by community platform (Discord roles, Reddit mod powers,
            etc.)
        invitation_reason (None | str | Unset): Reason/context for invitation
        reputation_in_community (int | None | Unset): Community-specific reputation
        invited_by (None | Unset | UUID): Profile ID of the user who invited this member
        is_active (bool | Unset): Whether membership is active Default: True.
        banned_at (datetime.datetime | None | Unset): Ban timestamp
        banned_reason (None | str | Unset): Reason for ban
        profile (None | Unset | UserProfileResponse): Associated user profile
        inviter (None | Unset | UserProfileResponse): Profile of the user who invited this member
    """

    created_at: datetime.datetime
    community_id: UUID
    id: UUID
    profile_id: UUID
    joined_at: datetime.datetime
    updated_at: datetime.datetime | None | Unset = UNSET
    is_external: bool | Unset = False
    role: CommunityRole | Unset = UNSET
    permissions: CommunityMemberResponsePermissionsType0 | None | Unset = UNSET
    invitation_reason: None | str | Unset = UNSET
    reputation_in_community: int | None | Unset = UNSET
    invited_by: None | Unset | UUID = UNSET
    is_active: bool | Unset = True
    banned_at: datetime.datetime | None | Unset = UNSET
    banned_reason: None | str | Unset = UNSET
    profile: None | Unset | UserProfileResponse = UNSET
    inviter: None | Unset | UserProfileResponse = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.community_member_response_permissions_type_0 import (
            CommunityMemberResponsePermissionsType0,
        )
        from ..models.user_profile_response import UserProfileResponse

        created_at = self.created_at.isoformat()

        community_id = str(self.community_id)

        id = str(self.id)

        profile_id = str(self.profile_id)

        joined_at = self.joined_at.isoformat()

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        is_external = self.is_external

        role: str | Unset = UNSET
        if not isinstance(self.role, Unset):
            role = self.role.value

        permissions: dict[str, Any] | None | Unset
        if isinstance(self.permissions, Unset):
            permissions = UNSET
        elif isinstance(self.permissions, CommunityMemberResponsePermissionsType0):
            permissions = self.permissions.to_dict()
        else:
            permissions = self.permissions

        invitation_reason: None | str | Unset
        if isinstance(self.invitation_reason, Unset):
            invitation_reason = UNSET
        else:
            invitation_reason = self.invitation_reason

        reputation_in_community: int | None | Unset
        if isinstance(self.reputation_in_community, Unset):
            reputation_in_community = UNSET
        else:
            reputation_in_community = self.reputation_in_community

        invited_by: None | str | Unset
        if isinstance(self.invited_by, Unset):
            invited_by = UNSET
        elif isinstance(self.invited_by, UUID):
            invited_by = str(self.invited_by)
        else:
            invited_by = self.invited_by

        is_active = self.is_active

        banned_at: None | str | Unset
        if isinstance(self.banned_at, Unset):
            banned_at = UNSET
        elif isinstance(self.banned_at, datetime.datetime):
            banned_at = self.banned_at.isoformat()
        else:
            banned_at = self.banned_at

        banned_reason: None | str | Unset
        if isinstance(self.banned_reason, Unset):
            banned_reason = UNSET
        else:
            banned_reason = self.banned_reason

        profile: dict[str, Any] | None | Unset
        if isinstance(self.profile, Unset):
            profile = UNSET
        elif isinstance(self.profile, UserProfileResponse):
            profile = self.profile.to_dict()
        else:
            profile = self.profile

        inviter: dict[str, Any] | None | Unset
        if isinstance(self.inviter, Unset):
            inviter = UNSET
        elif isinstance(self.inviter, UserProfileResponse):
            inviter = self.inviter.to_dict()
        else:
            inviter = self.inviter

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "created_at": created_at,
                "community_id": community_id,
                "id": id,
                "profile_id": profile_id,
                "joined_at": joined_at,
            }
        )
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if is_external is not UNSET:
            field_dict["is_external"] = is_external
        if role is not UNSET:
            field_dict["role"] = role
        if permissions is not UNSET:
            field_dict["permissions"] = permissions
        if invitation_reason is not UNSET:
            field_dict["invitation_reason"] = invitation_reason
        if reputation_in_community is not UNSET:
            field_dict["reputation_in_community"] = reputation_in_community
        if invited_by is not UNSET:
            field_dict["invited_by"] = invited_by
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if banned_at is not UNSET:
            field_dict["banned_at"] = banned_at
        if banned_reason is not UNSET:
            field_dict["banned_reason"] = banned_reason
        if profile is not UNSET:
            field_dict["profile"] = profile
        if inviter is not UNSET:
            field_dict["inviter"] = inviter

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_member_response_permissions_type_0 import (
            CommunityMemberResponsePermissionsType0,
        )
        from ..models.user_profile_response import UserProfileResponse

        d = dict(src_dict)
        created_at = isoparse(d.pop("created_at"))

        community_id = UUID(d.pop("community_id"))

        id = UUID(d.pop("id"))

        profile_id = UUID(d.pop("profile_id"))

        joined_at = isoparse(d.pop("joined_at"))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        is_external = d.pop("is_external", UNSET)

        _role = d.pop("role", UNSET)
        role: CommunityRole | Unset
        if isinstance(_role, Unset):
            role = UNSET
        else:
            role = CommunityRole(_role)

        def _parse_permissions(
            data: object,
        ) -> CommunityMemberResponsePermissionsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                permissions_type_0 = CommunityMemberResponsePermissionsType0.from_dict(
                    data
                )

                return permissions_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CommunityMemberResponsePermissionsType0 | None | Unset, data)

        permissions = _parse_permissions(d.pop("permissions", UNSET))

        def _parse_invitation_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        invitation_reason = _parse_invitation_reason(d.pop("invitation_reason", UNSET))

        def _parse_reputation_in_community(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reputation_in_community = _parse_reputation_in_community(
            d.pop("reputation_in_community", UNSET)
        )

        def _parse_invited_by(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                invited_by_type_0 = UUID(data)

                return invited_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        invited_by = _parse_invited_by(d.pop("invited_by", UNSET))

        is_active = d.pop("is_active", UNSET)

        def _parse_banned_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                banned_at_type_0 = isoparse(data)

                return banned_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        banned_at = _parse_banned_at(d.pop("banned_at", UNSET))

        def _parse_banned_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        banned_reason = _parse_banned_reason(d.pop("banned_reason", UNSET))

        def _parse_profile(data: object) -> None | Unset | UserProfileResponse:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                profile_type_0 = UserProfileResponse.from_dict(data)

                return profile_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserProfileResponse, data)

        profile = _parse_profile(d.pop("profile", UNSET))

        def _parse_inviter(data: object) -> None | Unset | UserProfileResponse:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                inviter_type_0 = UserProfileResponse.from_dict(data)

                return inviter_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UserProfileResponse, data)

        inviter = _parse_inviter(d.pop("inviter", UNSET))

        community_member_response = cls(
            created_at=created_at,
            community_id=community_id,
            id=id,
            profile_id=profile_id,
            joined_at=joined_at,
            updated_at=updated_at,
            is_external=is_external,
            role=role,
            permissions=permissions,
            invitation_reason=invitation_reason,
            reputation_in_community=reputation_in_community,
            invited_by=invited_by,
            is_active=is_active,
            banned_at=banned_at,
            banned_reason=banned_reason,
            profile=profile,
            inviter=inviter,
        )

        return community_member_response
