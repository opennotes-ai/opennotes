from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SimilarityMatch")


@_attrs_define
class SimilarityMatch:
    """Match result from similarity scan.

    Attributes:
        score (float): Similarity score
        matched_claim (str): Fact-check claim that matched
        matched_source (str): URL to the fact-check source
        scan_type (Literal['similarity'] | Unset):  Default: 'similarity'.
        fact_check_item_id (None | Unset | UUID): UUID of the matched FactCheckItem
    """

    score: float
    matched_claim: str
    matched_source: str
    scan_type: Literal["similarity"] | Unset = "similarity"
    fact_check_item_id: None | Unset | UUID = UNSET

    def to_dict(self) -> dict[str, Any]:
        score = self.score

        matched_claim = self.matched_claim

        matched_source = self.matched_source

        scan_type = self.scan_type

        fact_check_item_id: None | str | Unset
        if isinstance(self.fact_check_item_id, Unset):
            fact_check_item_id = UNSET
        elif isinstance(self.fact_check_item_id, UUID):
            fact_check_item_id = str(self.fact_check_item_id)
        else:
            fact_check_item_id = self.fact_check_item_id

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "score": score,
                "matched_claim": matched_claim,
                "matched_source": matched_source,
            }
        )
        if scan_type is not UNSET:
            field_dict["scan_type"] = scan_type
        if fact_check_item_id is not UNSET:
            field_dict["fact_check_item_id"] = fact_check_item_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        score = d.pop("score")

        matched_claim = d.pop("matched_claim")

        matched_source = d.pop("matched_source")

        scan_type = cast(Literal["similarity"] | Unset, d.pop("scan_type", UNSET))
        if scan_type != "similarity" and not isinstance(scan_type, Unset):
            raise ValueError(
                f"scan_type must match const 'similarity', got '{scan_type}'"
            )

        def _parse_fact_check_item_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                fact_check_item_id_type_0 = UUID(data)

                return fact_check_item_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        fact_check_item_id = _parse_fact_check_item_id(
            d.pop("fact_check_item_id", UNSET)
        )

        similarity_match = cls(
            score=score,
            matched_claim=matched_claim,
            matched_source=matched_source,
            scan_type=scan_type,
            fact_check_item_id=fact_check_item_id,
        )

        return similarity_match
