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

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.copy_requests_attributes import CopyRequestsAttributes


T = TypeVar("T", bound="CopyRequestsData")


@_attrs_define
class CopyRequestsData:
    """
    Attributes:
        attributes (CopyRequestsAttributes):
        type_ (Literal['copy-requests'] | Unset):  Default: 'copy-requests'.
    """

    attributes: CopyRequestsAttributes
    type_: Literal["copy-requests"] | Unset = "copy-requests"

    def to_dict(self) -> dict[str, Any]:
        attributes = self.attributes.to_dict()

        type_ = self.type_

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "attributes": attributes,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.copy_requests_attributes import CopyRequestsAttributes

        d = dict(src_dict)
        attributes = CopyRequestsAttributes.from_dict(d.pop("attributes"))

        type_ = cast(Literal["copy-requests"] | Unset, d.pop("type", UNSET))
        if type_ != "copy-requests" and not isinstance(type_, Unset):
            raise ValueError(f"type must match const 'copy-requests', got '{type_}'")

        copy_requests_data = cls(
            attributes=attributes,
            type_=type_,
        )

        return copy_requests_data
