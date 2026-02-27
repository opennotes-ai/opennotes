from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SetRatingAttributes")


@_attrs_define
class SetRatingAttributes:
    """Attributes for setting rating on a candidate via JSON:API.

    Attributes:
        rating (str): The rating to set
        rating_details (None | str | Unset): Original rating value if normalized
        auto_promote (bool | Unset): Whether to trigger promotion if candidate is ready Default: False.
    """

    rating: str
    rating_details: None | str | Unset = UNSET
    auto_promote: bool | Unset = False

    def to_dict(self) -> dict[str, Any]:
        rating = self.rating

        rating_details: None | str | Unset
        if isinstance(self.rating_details, Unset):
            rating_details = UNSET
        else:
            rating_details = self.rating_details

        auto_promote = self.auto_promote

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "rating": rating,
            }
        )
        if rating_details is not UNSET:
            field_dict["rating_details"] = rating_details
        if auto_promote is not UNSET:
            field_dict["auto_promote"] = auto_promote

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rating = d.pop("rating")

        def _parse_rating_details(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rating_details = _parse_rating_details(d.pop("rating_details", UNSET))

        auto_promote = d.pop("auto_promote", UNSET)

        set_rating_attributes = cls(
            rating=rating,
            rating_details=rating_details,
            auto_promote=auto_promote,
        )

        return set_rating_attributes
