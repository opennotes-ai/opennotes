from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.claim_category import ClaimCategory
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.supporting_fact import SupportingFact


T = TypeVar("T", bound="DedupedClaim")


@_attrs_define
class DedupedClaim:
    """
    Attributes:
        canonical_text (str):
        occurrence_count (int):
        author_count (int):
        utterance_ids (list[str]):
        representative_authors (list[str]):
        category (ClaimCategory | Unset): 5-way taxonomy for claim classification.

            Mirrors vibecheck-server's `ClaimCategory` so downstream premises/evidence
            tooling can use a shared vocabulary (TASK-1657.04 depends on these keys).
        supporting_facts (list[SupportingFact] | Unset):
        premise_ids (list[str] | Unset):
        facts_to_verify (int | Unset):  Default: 0.
    """

    canonical_text: str
    occurrence_count: int
    author_count: int
    utterance_ids: list[str]
    representative_authors: list[str]
    category: ClaimCategory | Unset = UNSET
    supporting_facts: list[SupportingFact] | Unset = UNSET
    premise_ids: list[str] | Unset = UNSET
    facts_to_verify: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        canonical_text = self.canonical_text

        occurrence_count = self.occurrence_count

        author_count = self.author_count

        utterance_ids = self.utterance_ids

        representative_authors = self.representative_authors

        category: str | Unset = UNSET
        if not isinstance(self.category, Unset):
            category = self.category.value

        supporting_facts: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.supporting_facts, Unset):
            supporting_facts = []
            for supporting_facts_item_data in self.supporting_facts:
                supporting_facts_item = supporting_facts_item_data.to_dict()
                supporting_facts.append(supporting_facts_item)

        premise_ids: list[str] | Unset = UNSET
        if not isinstance(self.premise_ids, Unset):
            premise_ids = self.premise_ids

        facts_to_verify = self.facts_to_verify

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "canonical_text": canonical_text,
                "occurrence_count": occurrence_count,
                "author_count": author_count,
                "utterance_ids": utterance_ids,
                "representative_authors": representative_authors,
            }
        )
        if category is not UNSET:
            field_dict["category"] = category
        if supporting_facts is not UNSET:
            field_dict["supporting_facts"] = supporting_facts
        if premise_ids is not UNSET:
            field_dict["premise_ids"] = premise_ids
        if facts_to_verify is not UNSET:
            field_dict["facts_to_verify"] = facts_to_verify

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.supporting_fact import SupportingFact

        d = dict(src_dict)
        canonical_text = d.pop("canonical_text")

        occurrence_count = d.pop("occurrence_count")

        author_count = d.pop("author_count")

        utterance_ids = cast(list[str], d.pop("utterance_ids"))

        representative_authors = cast(list[str], d.pop("representative_authors"))

        _category = d.pop("category", UNSET)
        category: ClaimCategory | Unset
        if isinstance(_category, Unset):
            category = UNSET
        else:
            category = ClaimCategory(_category)

        _supporting_facts = d.pop("supporting_facts", UNSET)
        supporting_facts: list[SupportingFact] | Unset = UNSET
        if _supporting_facts is not UNSET:
            supporting_facts = []
            for supporting_facts_item_data in _supporting_facts:
                supporting_facts_item = SupportingFact.from_dict(
                    supporting_facts_item_data
                )

                supporting_facts.append(supporting_facts_item)

        premise_ids = cast(list[str], d.pop("premise_ids", UNSET))

        facts_to_verify = d.pop("facts_to_verify", UNSET)

        deduped_claim = cls(
            canonical_text=canonical_text,
            occurrence_count=occurrence_count,
            author_count=author_count,
            utterance_ids=utterance_ids,
            representative_authors=representative_authors,
            category=category,
            supporting_facts=supporting_facts,
            premise_ids=premise_ids,
            facts_to_verify=facts_to_verify,
        )

        deduped_claim.additional_properties = d
        return deduped_claim

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
