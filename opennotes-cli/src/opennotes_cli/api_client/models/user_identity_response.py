from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.auth_provider import AuthProvider
from ..types import UNSET, Unset

T = TypeVar("T", bound="UserIdentityResponse")


@_attrs_define
class UserIdentityResponse:
    """API response schema for user identity (excludes sensitive fields).

    Attributes:
        created_at (datetime.datetime):
        id (UUID): Unique identity identifier
        profile_id (UUID): Associated user profile ID
        provider (AuthProvider): Supported authentication providers.
        provider_user_id (str): User's unique ID on the provider
        email_verified (bool): Whether email address is verified
        updated_at (datetime.datetime | None | Unset):
    """

    created_at: datetime.datetime
    id: UUID
    profile_id: UUID
    provider: AuthProvider
    provider_user_id: str
    email_verified: bool
    updated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        id = str(self.id)

        profile_id = str(self.profile_id)

        provider = self.provider.value

        provider_user_id = self.provider_user_id

        email_verified = self.email_verified

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created_at": created_at,
                "id": id,
                "profile_id": profile_id,
                "provider": provider,
                "provider_user_id": provider_user_id,
                "email_verified": email_verified,
            }
        )
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = isoparse(d.pop("created_at"))

        id = UUID(d.pop("id"))

        profile_id = UUID(d.pop("profile_id"))

        provider = AuthProvider(d.pop("provider"))

        provider_user_id = d.pop("provider_user_id")

        email_verified = d.pop("email_verified")

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

        user_identity_response = cls(
            created_at=created_at,
            id=id,
            profile_id=profile_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email_verified=email_verified,
            updated_at=updated_at,
        )

        user_identity_response.additional_properties = d
        return user_identity_response

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
