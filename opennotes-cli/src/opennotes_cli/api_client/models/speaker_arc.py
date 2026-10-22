from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SpeakerArc")


@_attrs_define
class SpeakerArc:
    """
    Attributes:
        speaker (str): Speaker label as it appears in the formatted transcript (e.g. 'alice', 'Speaker1').
        note (str): 1-2 sentence observation about this speaker's arc: how their tone, intent, or stance evolves across
            the conversation.
        utterance_id_range (list[int] | None | Unset): Inclusive [start, end] 1-indexed utterance index range that this
            arc covers, for timeline-viz alignment. Exactly two integers with start <= end and start >= 1.
    """

    speaker: str
    note: str
    utterance_id_range: list[int] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        speaker = self.speaker

        note = self.note

        utterance_id_range: list[int] | None | Unset
        if isinstance(self.utterance_id_range, Unset):
            utterance_id_range = UNSET
        elif isinstance(self.utterance_id_range, list):
            utterance_id_range = self.utterance_id_range

        else:
            utterance_id_range = self.utterance_id_range

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "speaker": speaker,
                "note": note,
            }
        )
        if utterance_id_range is not UNSET:
            field_dict["utterance_id_range"] = utterance_id_range

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        speaker = d.pop("speaker")

        note = d.pop("note")

        def _parse_utterance_id_range(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                utterance_id_range_type_0 = cast(list[int], data)

                return utterance_id_range_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        utterance_id_range = _parse_utterance_id_range(
            d.pop("utterance_id_range", UNSET)
        )

        speaker_arc = cls(
            speaker=speaker,
            note=note,
            utterance_id_range=utterance_id_range,
        )

        speaker_arc.additional_properties = d
        return speaker_arc

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
