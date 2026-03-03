from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.resume_data import ResumeData


T = TypeVar("T", bound="ResumeRequest")


@_attrs_define
class ResumeRequest:
    """
    Attributes:
        data (ResumeData):
    """

    data: ResumeData

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
        from ..models.resume_data import ResumeData

        d = dict(src_dict)
        data = ResumeData.from_dict(d.pop("data"))

        resume_request = cls(
            data=data,
        )

        return resume_request
