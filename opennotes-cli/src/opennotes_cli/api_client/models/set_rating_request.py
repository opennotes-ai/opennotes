from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.set_rating_data import SetRatingData


T = TypeVar("T", bound="SetRatingRequest")


@_attrs_define
class SetRatingRequest:
    """JSON:API request body for setting rating on a candidate.

    Attributes:
        data (SetRatingData): JSON:API data object for setting rating.
    """

    data: SetRatingData

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
        from ..models.set_rating_data import SetRatingData

        d = dict(src_dict)
        data = SetRatingData.from_dict(d.pop("data"))

        set_rating_request = cls(
            data=data,
        )

        return set_rating_request
