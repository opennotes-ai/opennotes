from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.identity_create_data import IdentityCreateData


T = TypeVar("T", bound="IdentityCreateRequest")


@_attrs_define
class IdentityCreateRequest:
    """JSON:API request for creating an identity.

    Attributes:
        data (IdentityCreateData): JSON:API data object for identity create request.
    """

    data: IdentityCreateData

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.identity_create_data import IdentityCreateData

        d = dict(src_dict)
        data = IdentityCreateData.from_dict(d.pop("data"))

        identity_create_request = cls(
            data=data,
        )

        return identity_create_request
