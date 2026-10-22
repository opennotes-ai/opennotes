from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ImageModerationMatch")


@_attrs_define
class ImageModerationMatch:
    """
    Attributes:
        utterance_id (str):
        image_url (str):
        adult (float):
        violence (float):
        racy (float):
        medical (float):
        spoof (float):
        flagged (bool):
        max_likelihood (float):
    """

    utterance_id: str
    image_url: str
    adult: float
    violence: float
    racy: float
    medical: float
    spoof: float
    flagged: bool
    max_likelihood: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        utterance_id = self.utterance_id

        image_url = self.image_url

        adult = self.adult

        violence = self.violence

        racy = self.racy

        medical = self.medical

        spoof = self.spoof

        flagged = self.flagged

        max_likelihood = self.max_likelihood

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "utterance_id": utterance_id,
                "image_url": image_url,
                "adult": adult,
                "violence": violence,
                "racy": racy,
                "medical": medical,
                "spoof": spoof,
                "flagged": flagged,
                "max_likelihood": max_likelihood,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        utterance_id = d.pop("utterance_id")

        image_url = d.pop("image_url")

        adult = d.pop("adult")

        violence = d.pop("violence")

        racy = d.pop("racy")

        medical = d.pop("medical")

        spoof = d.pop("spoof")

        flagged = d.pop("flagged")

        max_likelihood = d.pop("max_likelihood")

        image_moderation_match = cls(
            utterance_id=utterance_id,
            image_url=image_url,
            adult=adult,
            violence=violence,
            racy=racy,
            medical=medical,
            spoof=spoof,
            flagged=flagged,
            max_likelihood=max_likelihood,
        )

        image_moderation_match.additional_properties = d
        return image_moderation_match

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
