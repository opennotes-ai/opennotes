from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.premises_registry_premises import PremisesRegistryPremises


T = TypeVar("T", bound="PremisesRegistry")


@_attrs_define
class PremisesRegistry:
    """Global registry of unique premises discovered across all claims.

    Attributes:
        premises (PremisesRegistryPremises | Unset):
    """

    premises: PremisesRegistryPremises | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        premises: dict[str, Any] | Unset = UNSET
        if not isinstance(self.premises, Unset):
            premises = self.premises.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if premises is not UNSET:
            field_dict["premises"] = premises

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.premises_registry_premises import PremisesRegistryPremises

        d = dict(src_dict)
        _premises = d.pop("premises", UNSET)
        premises: PremisesRegistryPremises | Unset
        if isinstance(_premises, Unset):
            premises = UNSET
        else:
            premises = PremisesRegistryPremises.from_dict(_premises)

        premises_registry = cls(
            premises=premises,
        )

        premises_registry.additional_properties = d
        return premises_registry

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
