from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.utterance_stream_type import UtteranceStreamType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scd_report_per_speaker_notes import SCDReportPerSpeakerNotes
    from ..models.speaker_arc import SpeakerArc


T = TypeVar("T", bound="SCDReport")


@_attrs_define
class SCDReport:
    """
    Attributes:
        summary (str):
        narrative (str | Unset): Conversational-register narrative (~80-150 words) describing how the conversation
            unfolds. Default: ''.
        speaker_arcs (list[SpeakerArc] | Unset):
        tone_labels (list[str] | Unset):
        per_speaker_notes (SCDReportPerSpeakerNotes | Unset):
        insufficient_conversation (bool | Unset):  Default: False.
        upstream_stream_type (UtteranceStreamType | Unset): Discourse shape observed in the extracted utterance stream.
        observed_stream_type (UtteranceStreamType | Unset): Discourse shape observed in the extracted utterance stream.
        observed_confidence (float | Unset): Confidence in observed_stream_type, from 0.0 to 1.0. Default: 0.0.
        disagreement_rationale (str | Unset): Short rationale when observed_stream_type differs from
            upstream_stream_type. Default: ''.
    """

    summary: str
    narrative: str | Unset = ""
    speaker_arcs: list[SpeakerArc] | Unset = UNSET
    tone_labels: list[str] | Unset = UNSET
    per_speaker_notes: SCDReportPerSpeakerNotes | Unset = UNSET
    insufficient_conversation: bool | Unset = False
    upstream_stream_type: UtteranceStreamType | Unset = UNSET
    observed_stream_type: UtteranceStreamType | Unset = UNSET
    observed_confidence: float | Unset = 0.0
    disagreement_rationale: str | Unset = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary

        narrative = self.narrative

        speaker_arcs: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.speaker_arcs, Unset):
            speaker_arcs = []
            for speaker_arcs_item_data in self.speaker_arcs:
                speaker_arcs_item = speaker_arcs_item_data.to_dict()
                speaker_arcs.append(speaker_arcs_item)

        tone_labels: list[str] | Unset = UNSET
        if not isinstance(self.tone_labels, Unset):
            tone_labels = self.tone_labels

        per_speaker_notes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.per_speaker_notes, Unset):
            per_speaker_notes = self.per_speaker_notes.to_dict()

        insufficient_conversation = self.insufficient_conversation

        upstream_stream_type: str | Unset = UNSET
        if not isinstance(self.upstream_stream_type, Unset):
            upstream_stream_type = self.upstream_stream_type.value

        observed_stream_type: str | Unset = UNSET
        if not isinstance(self.observed_stream_type, Unset):
            observed_stream_type = self.observed_stream_type.value

        observed_confidence = self.observed_confidence

        disagreement_rationale = self.disagreement_rationale

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "summary": summary,
            }
        )
        if narrative is not UNSET:
            field_dict["narrative"] = narrative
        if speaker_arcs is not UNSET:
            field_dict["speaker_arcs"] = speaker_arcs
        if tone_labels is not UNSET:
            field_dict["tone_labels"] = tone_labels
        if per_speaker_notes is not UNSET:
            field_dict["per_speaker_notes"] = per_speaker_notes
        if insufficient_conversation is not UNSET:
            field_dict["insufficient_conversation"] = insufficient_conversation
        if upstream_stream_type is not UNSET:
            field_dict["upstream_stream_type"] = upstream_stream_type
        if observed_stream_type is not UNSET:
            field_dict["observed_stream_type"] = observed_stream_type
        if observed_confidence is not UNSET:
            field_dict["observed_confidence"] = observed_confidence
        if disagreement_rationale is not UNSET:
            field_dict["disagreement_rationale"] = disagreement_rationale

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scd_report_per_speaker_notes import SCDReportPerSpeakerNotes
        from ..models.speaker_arc import SpeakerArc

        d = dict(src_dict)
        summary = d.pop("summary")

        narrative = d.pop("narrative", UNSET)

        _speaker_arcs = d.pop("speaker_arcs", UNSET)
        speaker_arcs: list[SpeakerArc] | Unset = UNSET
        if _speaker_arcs is not UNSET:
            speaker_arcs = []
            for speaker_arcs_item_data in _speaker_arcs:
                speaker_arcs_item = SpeakerArc.from_dict(speaker_arcs_item_data)

                speaker_arcs.append(speaker_arcs_item)

        tone_labels = cast(list[str], d.pop("tone_labels", UNSET))

        _per_speaker_notes = d.pop("per_speaker_notes", UNSET)
        per_speaker_notes: SCDReportPerSpeakerNotes | Unset
        if isinstance(_per_speaker_notes, Unset):
            per_speaker_notes = UNSET
        else:
            per_speaker_notes = SCDReportPerSpeakerNotes.from_dict(_per_speaker_notes)

        insufficient_conversation = d.pop("insufficient_conversation", UNSET)

        _upstream_stream_type = d.pop("upstream_stream_type", UNSET)
        upstream_stream_type: UtteranceStreamType | Unset
        if isinstance(_upstream_stream_type, Unset):
            upstream_stream_type = UNSET
        else:
            upstream_stream_type = UtteranceStreamType(_upstream_stream_type)

        _observed_stream_type = d.pop("observed_stream_type", UNSET)
        observed_stream_type: UtteranceStreamType | Unset
        if isinstance(_observed_stream_type, Unset):
            observed_stream_type = UNSET
        else:
            observed_stream_type = UtteranceStreamType(_observed_stream_type)

        observed_confidence = d.pop("observed_confidence", UNSET)

        disagreement_rationale = d.pop("disagreement_rationale", UNSET)

        scd_report = cls(
            summary=summary,
            narrative=narrative,
            speaker_arcs=speaker_arcs,
            tone_labels=tone_labels,
            per_speaker_notes=per_speaker_notes,
            insufficient_conversation=insufficient_conversation,
            upstream_stream_type=upstream_stream_type,
            observed_stream_type=observed_stream_type,
            observed_confidence=observed_confidence,
            disagreement_rationale=disagreement_rationale,
        )

        scd_report.additional_properties = d
        return scd_report

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
