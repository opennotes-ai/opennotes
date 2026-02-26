from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.community_member_response import CommunityMemberResponse
    from ..models.user_identity_response import UserIdentityResponse


T = TypeVar("T", bound="UserProfileResponse")


@_attrs_define
class UserProfileResponse:
    """API response schema for user profile with nested relationships.

    Attributes:
        created_at (datetime.datetime):
        display_name (str): User's display name
        id (UUID): Unique profile identifier
        updated_at (datetime.datetime | None | Unset):
        avatar_url (None | str | Unset): URL to user's avatar image
        bio (None | str | Unset): User biography/description
        role (str | Unset): Platform-level role (user, moderator, admin) Default: 'user'.
        is_opennotes_admin (bool | Unset): OpenNotes-specific admin flag (grants cross-community admin privileges)
            Default: False.
        is_human (bool | Unset): Distinguishes human users from bot accounts Default: True.
        is_active (bool | Unset): Whether the profile is active Default: True.
        is_banned (bool | Unset): Whether the profile is banned Default: False.
        banned_at (datetime.datetime | None | Unset): Timestamp when profile was banned
        banned_reason (None | str | Unset): Reason for ban
        reputation (int | Unset): Global reputation score Default: 0.
        identities (list[UserIdentityResponse] | Unset): Linked authentication identities
        community_memberships (list[CommunityMemberResponse] | Unset): Community memberships
    """

    created_at: datetime.datetime
    display_name: str
    id: UUID
    updated_at: datetime.datetime | None | Unset = UNSET
    avatar_url: None | str | Unset = UNSET
    bio: None | str | Unset = UNSET
    role: str | Unset = "user"
    is_opennotes_admin: bool | Unset = False
    is_human: bool | Unset = True
    is_active: bool | Unset = True
    is_banned: bool | Unset = False
    banned_at: datetime.datetime | None | Unset = UNSET
    banned_reason: None | str | Unset = UNSET
    reputation: int | Unset = 0
    identities: list[UserIdentityResponse] | Unset = UNSET
    community_memberships: list[CommunityMemberResponse] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        display_name = self.display_name

        id = str(self.id)

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        avatar_url: None | str | Unset
        if isinstance(self.avatar_url, Unset):
            avatar_url = UNSET
        else:
            avatar_url = self.avatar_url

        bio: None | str | Unset
        if isinstance(self.bio, Unset):
            bio = UNSET
        else:
            bio = self.bio

        role = self.role

        is_opennotes_admin = self.is_opennotes_admin

        is_human = self.is_human

        is_active = self.is_active

        is_banned = self.is_banned

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

        reputation = self.reputation

        identities: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.identities, Unset):
            identities = []
            for identities_item_data in self.identities:
                identities_item = identities_item_data.to_dict()
                identities.append(identities_item)

        community_memberships: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.community_memberships, Unset):
            community_memberships = []
            for community_memberships_item_data in self.community_memberships:
                community_memberships_item = community_memberships_item_data.to_dict()
                community_memberships.append(community_memberships_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "created_at": created_at,
                "display_name": display_name,
                "id": id,
            }
        )
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if avatar_url is not UNSET:
            field_dict["avatar_url"] = avatar_url
        if bio is not UNSET:
            field_dict["bio"] = bio
        if role is not UNSET:
            field_dict["role"] = role
        if is_opennotes_admin is not UNSET:
            field_dict["is_opennotes_admin"] = is_opennotes_admin
        if is_human is not UNSET:
            field_dict["is_human"] = is_human
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if is_banned is not UNSET:
            field_dict["is_banned"] = is_banned
        if banned_at is not UNSET:
            field_dict["banned_at"] = banned_at
        if banned_reason is not UNSET:
            field_dict["banned_reason"] = banned_reason
        if reputation is not UNSET:
            field_dict["reputation"] = reputation
        if identities is not UNSET:
            field_dict["identities"] = identities
        if community_memberships is not UNSET:
            field_dict["community_memberships"] = community_memberships

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.community_member_response import CommunityMemberResponse
        from ..models.user_identity_response import UserIdentityResponse

        d = dict(src_dict)
        created_at = isoparse(d.pop("created_at"))

        display_name = d.pop("display_name")

        id = UUID(d.pop("id"))

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

        def _parse_avatar_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        avatar_url = _parse_avatar_url(d.pop("avatar_url", UNSET))

        def _parse_bio(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bio = _parse_bio(d.pop("bio", UNSET))

        role = d.pop("role", UNSET)

        is_opennotes_admin = d.pop("is_opennotes_admin", UNSET)

        is_human = d.pop("is_human", UNSET)

        is_active = d.pop("is_active", UNSET)

        is_banned = d.pop("is_banned", UNSET)

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

        reputation = d.pop("reputation", UNSET)

        _identities = d.pop("identities", UNSET)
        identities: list[UserIdentityResponse] | Unset = UNSET
        if _identities is not UNSET:
            identities = []
            for identities_item_data in _identities:
                identities_item = UserIdentityResponse.from_dict(identities_item_data)

                identities.append(identities_item)

        _community_memberships = d.pop("community_memberships", UNSET)
        community_memberships: list[CommunityMemberResponse] | Unset = UNSET
        if _community_memberships is not UNSET:
            community_memberships = []
            for community_memberships_item_data in _community_memberships:
                community_memberships_item = CommunityMemberResponse.from_dict(
                    community_memberships_item_data
                )

                community_memberships.append(community_memberships_item)

        user_profile_response = cls(
            created_at=created_at,
            display_name=display_name,
            id=id,
            updated_at=updated_at,
            avatar_url=avatar_url,
            bio=bio,
            role=role,
            is_opennotes_admin=is_opennotes_admin,
            is_human=is_human,
            is_active=is_active,
            is_banned=is_banned,
            banned_at=banned_at,
            banned_reason=banned_reason,
            reputation=reputation,
            identities=identities,
            community_memberships=community_memberships,
        )

        return user_profile_response
