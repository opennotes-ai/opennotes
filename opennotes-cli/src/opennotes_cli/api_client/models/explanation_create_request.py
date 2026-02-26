from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.explanation_create_data import ExplanationCreateData


T = TypeVar("T", bound="ExplanationCreateRequest")


@_attrs_define
class ExplanationCreateRequest:
    """JSON:API request body for generating a scan explanation.

    Attributes:
        data (ExplanationCreateData): JSON:API data object for explanation generation.
    """

    data: ExplanationCreateData

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
        from ..models.explanation_create_data import ExplanationCreateData

        d = dict(src_dict)
        data = ExplanationCreateData.from_dict(d.pop("data"))

        explanation_create_request = cls(
            data=data,
        )

        return explanation_create_request
