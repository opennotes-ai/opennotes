from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.batch_score_request_data import BatchScoreRequestData


T = TypeVar("T", bound="BatchScoreRequest")


@_attrs_define
class BatchScoreRequest:
    """JSON:API request body for batch scores.

    Attributes:
        data (BatchScoreRequestData): JSON:API data object for batch score request.
    """

    data: BatchScoreRequestData

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
        from ..models.batch_score_request_data import BatchScoreRequestData

        d = dict(src_dict)
        data = BatchScoreRequestData.from_dict(d.pop("data"))

        batch_score_request = cls(
            data=data,
        )

        return batch_score_request
