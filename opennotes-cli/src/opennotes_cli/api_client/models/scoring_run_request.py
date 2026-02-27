from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.scoring_run_request_data import ScoringRunRequestData


T = TypeVar("T", bound="ScoringRunRequest")


@_attrs_define
class ScoringRunRequest:
    """JSON:API request body for scoring run.

    Attributes:
        data (ScoringRunRequestData): JSON:API data object for scoring run request.
    """

    data: ScoringRunRequestData

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
        from ..models.scoring_run_request_data import ScoringRunRequestData

        d = dict(src_dict)
        data = ScoringRunRequestData.from_dict(d.pop("data"))

        scoring_run_request = cls(
            data=data,
        )

        return scoring_run_request
