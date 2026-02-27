from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.request_create_attributes import RequestCreateAttributes


T = TypeVar("T", bound="RequestCreateData")


@_attrs_define
class RequestCreateData:
    """JSON:API data object for request creation.

    Attributes:
        type_ (Literal['requests']): Resource type must be 'requests'
        attributes (RequestCreateAttributes): Attributes for creating a request via JSON:API.
    """

    type_: Literal["requests"]
    attributes: RequestCreateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.request_create_attributes import RequestCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["requests"], d.pop("type"))
        if type_ != "requests":
            raise ValueError(f"type must match const 'requests', got '{type_}'")

        attributes = RequestCreateAttributes.from_dict(d.pop("attributes"))

        request_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return request_create_data
