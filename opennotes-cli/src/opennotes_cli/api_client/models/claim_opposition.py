from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClaimOpposition")


@_attrs_define
class ClaimOpposition:
    """
    Attributes:
        topic (str):
        supporting_cluster_texts (list[str]):
        opposing_cluster_texts (list[str]):
        note (None | str | Unset):
    """

    topic: str
    supporting_cluster_texts: list[str]
    opposing_cluster_texts: list[str]
    note: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        topic = self.topic

        supporting_cluster_texts = self.supporting_cluster_texts

        opposing_cluster_texts = self.opposing_cluster_texts

        note: None | str | Unset
        if isinstance(self.note, Unset):
            note = UNSET
        else:
            note = self.note

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "topic": topic,
                "supporting_cluster_texts": supporting_cluster_texts,
                "opposing_cluster_texts": opposing_cluster_texts,
            }
        )
        if note is not UNSET:
            field_dict["note"] = note

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        topic = d.pop("topic")

        supporting_cluster_texts = cast(list[str], d.pop("supporting_cluster_texts"))

        opposing_cluster_texts = cast(list[str], d.pop("opposing_cluster_texts"))

        def _parse_note(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        note = _parse_note(d.pop("note", UNSET))

        claim_opposition = cls(
            topic=topic,
            supporting_cluster_texts=supporting_cluster_texts,
            opposing_cluster_texts=opposing_cluster_texts,
            note=note,
        )

        claim_opposition.additional_properties = d
        return claim_opposition

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
