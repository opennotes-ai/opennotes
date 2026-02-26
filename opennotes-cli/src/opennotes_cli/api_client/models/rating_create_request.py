from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.rating_create_data import RatingCreateData


T = TypeVar("T", bound="RatingCreateRequest")


@_attrs_define
class RatingCreateRequest:
    """JSON:API request body for creating a rating.

    Attributes:
        data (RatingCreateData): JSON:API data object for rating creation.
    """

    data: RatingCreateData

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
        from ..models.rating_create_data import RatingCreateData

        d = dict(src_dict)
        data = RatingCreateData.from_dict(d.pop("data"))

        rating_create_request = cls(
            data=data,
        )

        return rating_create_request
