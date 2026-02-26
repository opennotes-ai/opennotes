from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClaimRelevanceCheckResultAttributes")


@_attrs_define
class ClaimRelevanceCheckResultAttributes:
    """Attributes for claim relevance check result.

    Attributes:
        outcome (str): Relevance check outcome: relevant, not_relevant, indeterminate, or content_filtered
        reasoning (str): Explanation of the relevance decision
        should_flag (bool): Whether the message should be flagged (true for relevant or indeterminate outcomes)
    """

    outcome: str
    reasoning: str
    should_flag: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        outcome = self.outcome

        reasoning = self.reasoning

        should_flag = self.should_flag

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "outcome": outcome,
                "reasoning": reasoning,
                "should_flag": should_flag,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        outcome = d.pop("outcome")

        reasoning = d.pop("reasoning")

        should_flag = d.pop("should_flag")

        claim_relevance_check_result_attributes = cls(
            outcome=outcome,
            reasoning=reasoning,
            should_flag=should_flag,
        )

        claim_relevance_check_result_attributes.additional_properties = d
        return claim_relevance_check_result_attributes

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
