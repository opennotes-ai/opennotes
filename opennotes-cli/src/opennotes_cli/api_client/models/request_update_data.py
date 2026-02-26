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
    from ..models.request_update_attributes import RequestUpdateAttributes


T = TypeVar("T", bound="RequestUpdateData")


@_attrs_define
class RequestUpdateData:
    """JSON:API data object for request update.

    Attributes:
        type_ (Literal['requests']): Resource type must be 'requests'
        id (str): Request ID being updated
        attributes (RequestUpdateAttributes): Attributes for updating a request via JSON:API.
    """

    type_: Literal["requests"]
    id: str
    attributes: RequestUpdateAttributes

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        id = self.id

        attributes = self.attributes.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "type": type_,
                "id": id,
                "attributes": attributes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.request_update_attributes import RequestUpdateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["requests"], d.pop("type"))
        if type_ != "requests":
            raise ValueError(f"type must match const 'requests', got '{type_}'")

        id = d.pop("id")

        attributes = RequestUpdateAttributes.from_dict(d.pop("attributes"))

        request_update_data = cls(
            type_=type_,
            id=id,
            attributes=attributes,
        )

        return request_update_data
