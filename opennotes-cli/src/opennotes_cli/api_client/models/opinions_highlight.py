from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.deduped_claim import DedupedClaim


T = TypeVar("T", bound="OpinionsHighlight")


@_attrs_define
class OpinionsHighlight:
    """
    Attributes:
        cluster (DedupedClaim):
        crossed_scaled_threshold (bool):
    """

    cluster: DedupedClaim
    crossed_scaled_threshold: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cluster = self.cluster.to_dict()

        crossed_scaled_threshold = self.crossed_scaled_threshold

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cluster": cluster,
                "crossed_scaled_threshold": crossed_scaled_threshold,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deduped_claim import DedupedClaim

        d = dict(src_dict)
        cluster = DedupedClaim.from_dict(d.pop("cluster"))

        crossed_scaled_threshold = d.pop("crossed_scaled_threshold")

        opinions_highlight = cls(
            cluster=cluster,
            crossed_scaled_threshold=crossed_scaled_threshold,
        )

        opinions_highlight.additional_properties = d
        return opinions_highlight

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
