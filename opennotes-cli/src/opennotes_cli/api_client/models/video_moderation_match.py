from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.frame_finding import FrameFinding


T = TypeVar("T", bound="VideoModerationMatch")


@_attrs_define
class VideoModerationMatch:
    """
    Attributes:
        utterance_id (str):
        video_url (str):
        flagged (bool):
        max_likelihood (float):
        frame_findings (list[FrameFinding] | Unset):
    """

    utterance_id: str
    video_url: str
    flagged: bool
    max_likelihood: float
    frame_findings: list[FrameFinding] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        utterance_id = self.utterance_id

        video_url = self.video_url

        flagged = self.flagged

        max_likelihood = self.max_likelihood

        frame_findings: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.frame_findings, Unset):
            frame_findings = []
            for frame_findings_item_data in self.frame_findings:
                frame_findings_item = frame_findings_item_data.to_dict()
                frame_findings.append(frame_findings_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "utterance_id": utterance_id,
                "video_url": video_url,
                "flagged": flagged,
                "max_likelihood": max_likelihood,
            }
        )
        if frame_findings is not UNSET:
            field_dict["frame_findings"] = frame_findings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.frame_finding import FrameFinding

        d = dict(src_dict)
        utterance_id = d.pop("utterance_id")

        video_url = d.pop("video_url")

        flagged = d.pop("flagged")

        max_likelihood = d.pop("max_likelihood")

        _frame_findings = d.pop("frame_findings", UNSET)
        frame_findings: list[FrameFinding] | Unset = UNSET
        if _frame_findings is not UNSET:
            frame_findings = []
            for frame_findings_item_data in _frame_findings:
                frame_findings_item = FrameFinding.from_dict(frame_findings_item_data)

                frame_findings.append(frame_findings_item)

        video_moderation_match = cls(
            utterance_id=utterance_id,
            video_url=video_url,
            flagged=flagged,
            max_likelihood=max_likelihood,
            frame_findings=frame_findings,
        )

        video_moderation_match.additional_properties = d
        return video_moderation_match

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
