from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.previously_seen_check_data import PreviouslySeenCheckData


T = TypeVar("T", bound="PreviouslySeenCheckRequest")


@_attrs_define
class PreviouslySeenCheckRequest:
    """JSON:API request body for checking previously seen messages.

    Attributes:
        data (PreviouslySeenCheckData): JSON:API data object for previously seen message check.
    """

    data: PreviouslySeenCheckData

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
        from ..models.previously_seen_check_data import PreviouslySeenCheckData

        d = dict(src_dict)
        data = PreviouslySeenCheckData.from_dict(d.pop("data"))

        previously_seen_check_request = cls(
            data=data,
        )

        return previously_seen_check_request
