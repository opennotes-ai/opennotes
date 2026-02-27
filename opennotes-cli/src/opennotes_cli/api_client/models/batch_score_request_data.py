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
    from ..models.batch_score_request_attributes import BatchScoreRequestAttributes


T = TypeVar("T", bound="BatchScoreRequestData")


@_attrs_define
class BatchScoreRequestData:
    """JSON:API data object for batch score request.

    Attributes:
        type_ (Literal['batch-score-requests']): Resource type must be 'batch-score-requests'
        attributes (BatchScoreRequestAttributes): Attributes for batch score request via JSON:API.
    """

    type_: Literal["batch-score-requests"]
    attributes: BatchScoreRequestAttributes

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
        from ..models.batch_score_request_attributes import BatchScoreRequestAttributes

        d = dict(src_dict)
        type_ = cast(Literal["batch-score-requests"], d.pop("type"))
        if type_ != "batch-score-requests":
            raise ValueError(
                f"type must match const 'batch-score-requests', got '{type_}'"
            )

        attributes = BatchScoreRequestAttributes.from_dict(d.pop("attributes"))

        batch_score_request_data = cls(
            type_=type_,
            attributes=attributes,
        )

        return batch_score_request_data
