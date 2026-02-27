from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define

from ..models.risk_level import RiskLevel
from ..types import UNSET, Unset

T = TypeVar("T", bound="ConversationFlashpointMatch")


@_attrs_define
class ConversationFlashpointMatch:
    """Match result from conversation flashpoint detection scan.

    Attributes:
        derailment_score (int): Derailment risk score (0-100)
        risk_level (RiskLevel): Categorical risk level for conversation flashpoint detection.
        reasoning (str): Explanation of detected escalation signals
        context_messages (int): Number of context messages analyzed
        scan_type (Literal['conversation_flashpoint'] | Unset):  Default: 'conversation_flashpoint'.
    """

    derailment_score: int
    risk_level: RiskLevel
    reasoning: str
    context_messages: int
    scan_type: Literal["conversation_flashpoint"] | Unset = "conversation_flashpoint"

    def to_dict(self) -> dict[str, Any]:
        derailment_score = self.derailment_score

        risk_level = self.risk_level.value

        reasoning = self.reasoning

        context_messages = self.context_messages

        scan_type = self.scan_type

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "derailment_score": derailment_score,
                "risk_level": risk_level,
                "reasoning": reasoning,
                "context_messages": context_messages,
            }
        )
        if scan_type is not UNSET:
            field_dict["scan_type"] = scan_type

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        derailment_score = d.pop("derailment_score")

        risk_level = RiskLevel(d.pop("risk_level"))

        reasoning = d.pop("reasoning")

        context_messages = d.pop("context_messages")

        scan_type = cast(
            Literal["conversation_flashpoint"] | Unset, d.pop("scan_type", UNSET)
        )
        if scan_type != "conversation_flashpoint" and not isinstance(scan_type, Unset):
            raise ValueError(
                f"scan_type must match const 'conversation_flashpoint', got '{scan_type}'"
            )

        conversation_flashpoint_match = cls(
            derailment_score=derailment_score,
            risk_level=risk_level,
            reasoning=reasoning,
            context_messages=context_messages,
            scan_type=scan_type,
        )

        return conversation_flashpoint_match
