from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.identity_create_attributes_credentials_type_0 import (
        IdentityCreateAttributesCredentialsType0,
    )


T = TypeVar("T", bound="IdentityCreateAttributes")


@_attrs_define
class IdentityCreateAttributes:
    """Attributes for identity create request.

    Attributes:
        provider (str):
        provider_user_id (str):
        credentials (IdentityCreateAttributesCredentialsType0 | None | Unset):
    """

    provider: str
    provider_user_id: str
    credentials: IdentityCreateAttributesCredentialsType0 | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.identity_create_attributes_credentials_type_0 import (
            IdentityCreateAttributesCredentialsType0,
        )

        provider = self.provider

        provider_user_id = self.provider_user_id

        credentials: dict[str, Any] | None | Unset
        if isinstance(self.credentials, Unset):
            credentials = UNSET
        elif isinstance(self.credentials, IdentityCreateAttributesCredentialsType0):
            credentials = self.credentials.to_dict()
        else:
            credentials = self.credentials

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "provider": provider,
                "provider_user_id": provider_user_id,
            }
        )
        if credentials is not UNSET:
            field_dict["credentials"] = credentials

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.identity_create_attributes_credentials_type_0 import (
            IdentityCreateAttributesCredentialsType0,
        )

        d = dict(src_dict)
        provider = d.pop("provider")

        provider_user_id = d.pop("provider_user_id")

        def _parse_credentials(
            data: object,
        ) -> IdentityCreateAttributesCredentialsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                credentials_type_0 = IdentityCreateAttributesCredentialsType0.from_dict(
                    data
                )

                return credentials_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IdentityCreateAttributesCredentialsType0 | None | Unset, data)

        credentials = _parse_credentials(d.pop("credentials", UNSET))

        identity_create_attributes = cls(
            provider=provider,
            provider_user_id=provider_user_id,
            credentials=credentials,
        )

        return identity_create_attributes
