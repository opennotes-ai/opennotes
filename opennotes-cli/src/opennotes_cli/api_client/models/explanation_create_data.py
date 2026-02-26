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
    from ..models.explanation_create_attributes import ExplanationCreateAttributes


T = TypeVar("T", bound="ExplanationCreateData")


@_attrs_define
class ExplanationCreateData:
    """JSON:API data object for explanation generation.

    Attributes:
        type_ (Literal['scan-explanations']): Resource type must be 'scan-explanations'
        attributes (ExplanationCreateAttributes): Attributes for generating a scan explanation.
    """

    type_: Literal["scan-explanations"]
    attributes: ExplanationCreateAttributes

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
        from ..models.explanation_create_attributes import ExplanationCreateAttributes

        d = dict(src_dict)
        type_ = cast(Literal["scan-explanations"], d.pop("type"))
        if type_ != "scan-explanations":
            raise ValueError(
                f"type must match const 'scan-explanations', got '{type_}'"
            )

        attributes = ExplanationCreateAttributes.from_dict(d.pop("attributes"))

        explanation_create_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return explanation_create_data
