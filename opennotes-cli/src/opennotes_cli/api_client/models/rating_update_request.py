from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.rating_update_data import RatingUpdateData


T = TypeVar("T", bound="RatingUpdateRequest")


@_attrs_define
class RatingUpdateRequest:
    """JSON:API request body for updating a rating.

    Attributes:
        data (RatingUpdateData): JSON:API data object for rating update.
    """

    data: RatingUpdateData

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
        from ..models.rating_update_data import RatingUpdateData

        d = dict(src_dict)
        data = RatingUpdateData.from_dict(d.pop("data"))

        rating_update_request = cls(
            data=data,
        )

        return rating_update_request
