from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.note_stats_attributes import NoteStatsAttributes


T = TypeVar("T", bound="NoteStatsResource")


@_attrs_define
class NoteStatsResource:
    """JSON:API resource object for note statistics.

    Attributes:
        attributes (NoteStatsAttributes): Attributes for note statistics resource.
        type_ (str | Unset):  Default: 'note-stats'.
        id (str | Unset):  Default: 'aggregate'.
    """

    attributes: NoteStatsAttributes
    type_: str | Unset = "note-stats"
    id: str | Unset = "aggregate"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attributes = self.attributes.to_dict()

        type_ = self.type_

        id = self.id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attributes": attributes,
            }
        )
        if type_ is not UNSET:
            field_dict["type"] = type_
        if id is not UNSET:
            field_dict["id"] = id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.note_stats_attributes import NoteStatsAttributes

        d = dict(src_dict)
        attributes = NoteStatsAttributes.from_dict(d.pop("attributes"))

        type_ = d.pop("type", UNSET)

        id = d.pop("id", UNSET)

        note_stats_resource = cls(
            attributes=attributes,
            type_=type_,
            id=id,
        )

        note_stats_resource.additional_properties = d
        return note_stats_resource

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
