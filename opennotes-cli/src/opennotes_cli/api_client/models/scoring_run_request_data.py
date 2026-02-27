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
    from ..models.scoring_run_request_attributes import ScoringRunRequestAttributes


T = TypeVar("T", bound="ScoringRunRequestData")


@_attrs_define
class ScoringRunRequestData:
    """JSON:API data object for scoring run request.

    Attributes:
        type_ (Literal['scoring-requests']): Resource type must be 'scoring-requests'
        attributes (ScoringRunRequestAttributes): Attributes for scoring run request via JSON:API.
    """

    type_: Literal["scoring-requests"]
    attributes: ScoringRunRequestAttributes

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
        from ..models.scoring_run_request_attributes import ScoringRunRequestAttributes

        d = dict(src_dict)
        type_ = cast(Literal["scoring-requests"], d.pop("type"))
        if type_ != "scoring-requests":
            raise ValueError(f"type must match const 'scoring-requests', got '{type_}'")

        attributes = ScoringRunRequestAttributes.from_dict(d.pop("attributes"))

        scoring_run_request_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return scoring_run_request_data
