from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.previously_seen_message_create_data import (
        PreviouslySeenMessageCreateData,
    )


T = TypeVar("T", bound="PreviouslySeenMessageCreateRequest")


@_attrs_define
class PreviouslySeenMessageCreateRequest:
    """JSON:API request body for creating a previously seen message.

    Attributes:
        data (PreviouslySeenMessageCreateData): JSON:API data object for previously seen message creation.
    """

    data: PreviouslySeenMessageCreateData

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
        from ..models.previously_seen_message_create_data import (
            PreviouslySeenMessageCreateData,
        )

        d = dict(src_dict)
        data = PreviouslySeenMessageCreateData.from_dict(d.pop("data"))

        previously_seen_message_create_request = cls(
            data=data,
        )

        return previously_seen_message_create_request
