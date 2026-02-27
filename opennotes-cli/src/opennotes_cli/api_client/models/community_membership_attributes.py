from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="CommunityMembershipAttributes")


@_attrs_define
class CommunityMembershipAttributes:
    """Community membership attributes for JSON:API resource.

    Attributes:
        community_id (str):
        role (str):
        is_external (bool | Unset):  Default: False.
        is_active (bool | Unset):  Default: True.
        joined_at (datetime.datetime | None | Unset):
        reputation_in_community (int | None | Unset):
    """

    community_id: str
    role: str
    is_external: bool | Unset = False
    is_active: bool | Unset = True
    joined_at: datetime.datetime | None | Unset = UNSET
    reputation_in_community: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        community_id = self.community_id

        role = self.role

        is_external = self.is_external

        is_active = self.is_active

        joined_at: None | str | Unset
        if isinstance(self.joined_at, Unset):
            joined_at = UNSET
        elif isinstance(self.joined_at, datetime.datetime):
            joined_at = self.joined_at.isoformat()
        else:
            joined_at = self.joined_at

        reputation_in_community: int | None | Unset
        if isinstance(self.reputation_in_community, Unset):
            reputation_in_community = UNSET
        else:
            reputation_in_community = self.reputation_in_community

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "community_id": community_id,
                "role": role,
            }
        )
        if is_external is not UNSET:
            field_dict["is_external"] = is_external
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if joined_at is not UNSET:
            field_dict["joined_at"] = joined_at
        if reputation_in_community is not UNSET:
            field_dict["reputation_in_community"] = reputation_in_community

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        community_id = d.pop("community_id")

        role = d.pop("role")

        is_external = d.pop("is_external", UNSET)

        is_active = d.pop("is_active", UNSET)

        def _parse_joined_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                joined_at_type_0 = isoparse(data)

                return joined_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        joined_at = _parse_joined_at(d.pop("joined_at", UNSET))

        def _parse_reputation_in_community(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        reputation_in_community = _parse_reputation_in_community(
            d.pop("reputation_in_community", UNSET)
        )

        community_membership_attributes = cls(
            community_id=community_id,
            role=role,
            is_external=is_external,
            is_active=is_active,
            joined_at=joined_at,
            reputation_in_community=reputation_in_community,
        )

        community_membership_attributes.additional_properties = d
        return community_membership_attributes

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
