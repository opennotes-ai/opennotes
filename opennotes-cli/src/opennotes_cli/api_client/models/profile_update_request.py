from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.profile_update_data import ProfileUpdateData


T = TypeVar("T", bound="ProfileUpdateRequest")


@_attrs_define
class ProfileUpdateRequest:
    """JSON:API request for updating a profile.

    Attributes:
        data (ProfileUpdateData): JSON:API data object for profile update request.
    """

    data: ProfileUpdateData

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
        from ..models.profile_update_data import ProfileUpdateData

        d = dict(src_dict)
        data = ProfileUpdateData.from_dict(d.pop("data"))

        profile_update_request = cls(
            data=data,
        )

        return profile_update_request
