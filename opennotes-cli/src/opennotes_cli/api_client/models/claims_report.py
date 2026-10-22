from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.deduped_claim import DedupedClaim
    from ..models.premises_registry import PremisesRegistry


T = TypeVar("T", bound="ClaimsReport")


@_attrs_define
class ClaimsReport:
    """
    Attributes:
        deduped_claims (list[DedupedClaim]):
        total_claims (int):
        total_unique (int):
        premises (None | PremisesRegistry | Unset):
    """

    deduped_claims: list[DedupedClaim]
    total_claims: int
    total_unique: int
    premises: None | PremisesRegistry | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.premises_registry import PremisesRegistry

        deduped_claims = []
        for deduped_claims_item_data in self.deduped_claims:
            deduped_claims_item = deduped_claims_item_data.to_dict()
            deduped_claims.append(deduped_claims_item)

        total_claims = self.total_claims

        total_unique = self.total_unique

        premises: dict[str, Any] | None | Unset
        if isinstance(self.premises, Unset):
            premises = UNSET
        elif isinstance(self.premises, PremisesRegistry):
            premises = self.premises.to_dict()
        else:
            premises = self.premises

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deduped_claims": deduped_claims,
                "total_claims": total_claims,
                "total_unique": total_unique,
            }
        )
        if premises is not UNSET:
            field_dict["premises"] = premises

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deduped_claim import DedupedClaim
        from ..models.premises_registry import PremisesRegistry

        d = dict(src_dict)
        deduped_claims = []
        _deduped_claims = d.pop("deduped_claims")
        for deduped_claims_item_data in _deduped_claims:
            deduped_claims_item = DedupedClaim.from_dict(deduped_claims_item_data)

            deduped_claims.append(deduped_claims_item)

        total_claims = d.pop("total_claims")

        total_unique = d.pop("total_unique")

        def _parse_premises(data: object) -> None | PremisesRegistry | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                premises_type_0 = PremisesRegistry.from_dict(data)

                return premises_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PremisesRegistry | Unset, data)

        premises = _parse_premises(d.pop("premises", UNSET))

        claims_report = cls(
            deduped_claims=deduped_claims,
            total_claims=total_claims,
            total_unique=total_unique,
            premises=premises,
        )

        claims_report.additional_properties = d
        return claims_report

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
