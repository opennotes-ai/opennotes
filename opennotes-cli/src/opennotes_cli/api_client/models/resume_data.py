from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.resume_attributes import ResumeAttributes


T = TypeVar("T", bound="ResumeData")


@_attrs_define
class ResumeData:
    """
    Attributes:
        attributes (ResumeAttributes):
        type_ (str | Unset):  Default: 'simulations'.
    """

    attributes: ResumeAttributes
    type_: str | Unset = "simulations"

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
        from ..models.resume_attributes import ResumeAttributes

        d = dict(src_dict)
        attributes = ResumeAttributes.from_dict(d.pop("attributes"))

        type_ = d.pop("type", UNSET)

        resume_data = cls(
            attributes=attributes,
            type_=type_,
        )

        return resume_data
