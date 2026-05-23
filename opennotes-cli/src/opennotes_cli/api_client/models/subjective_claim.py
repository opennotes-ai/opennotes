from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.subjective_claim_stance import SubjectiveClaimStance

T = TypeVar("T", bound="SubjectiveClaim")


@_attrs_define
class SubjectiveClaim:
    """
    Attributes:
        claim_text (str):
        utterance_id (str):
        stance (SubjectiveClaimStance):
    """

    claim_text: str
    utterance_id: str
    stance: SubjectiveClaimStance
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim_text = self.claim_text

        utterance_id = self.utterance_id

        stance = self.stance.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claim_text": claim_text,
                "utterance_id": utterance_id,
                "stance": stance,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        claim_text = d.pop("claim_text")

        utterance_id = d.pop("utterance_id")

        stance = SubjectiveClaimStance(d.pop("stance"))

        subjective_claim = cls(
            claim_text=claim_text,
            utterance_id=utterance_id,
            stance=stance,
        )

        subjective_claim.additional_properties = d
        return subjective_claim

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
