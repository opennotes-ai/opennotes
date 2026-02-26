from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previously_seen_match_resource import PreviouslySeenMatchResource


T = TypeVar("T", bound="PreviouslySeenCheckResultAttributes")


@_attrs_define
class PreviouslySeenCheckResultAttributes:
    """Attributes for previously seen check result.

    Attributes:
        should_auto_publish (bool):
        should_auto_request (bool):
        autopublish_threshold (float):
        autorequest_threshold (float):
        matches (list[PreviouslySeenMatchResource]):
        top_match (None | PreviouslySeenMatchResource | Unset):
    """

    should_auto_publish: bool
    should_auto_request: bool
    autopublish_threshold: float
    autorequest_threshold: float
    matches: list[PreviouslySeenMatchResource]
    top_match: None | PreviouslySeenMatchResource | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.previously_seen_match_resource import PreviouslySeenMatchResource

        should_auto_publish = self.should_auto_publish

        should_auto_request = self.should_auto_request

        autopublish_threshold = self.autopublish_threshold

        autorequest_threshold = self.autorequest_threshold

        matches = []
        for matches_item_data in self.matches:
            matches_item = matches_item_data.to_dict()
            matches.append(matches_item)

        top_match: dict[str, Any] | None | Unset
        if isinstance(self.top_match, Unset):
            top_match = UNSET
        elif isinstance(self.top_match, PreviouslySeenMatchResource):
            top_match = self.top_match.to_dict()
        else:
            top_match = self.top_match

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "should_auto_publish": should_auto_publish,
                "should_auto_request": should_auto_request,
                "autopublish_threshold": autopublish_threshold,
                "autorequest_threshold": autorequest_threshold,
                "matches": matches,
            }
        )
        if top_match is not UNSET:
            field_dict["top_match"] = top_match

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previously_seen_match_resource import PreviouslySeenMatchResource

        d = dict(src_dict)
        should_auto_publish = d.pop("should_auto_publish")

        should_auto_request = d.pop("should_auto_request")

        autopublish_threshold = d.pop("autopublish_threshold")

        autorequest_threshold = d.pop("autorequest_threshold")

        matches = []
        _matches = d.pop("matches")
        for matches_item_data in _matches:
            matches_item = PreviouslySeenMatchResource.from_dict(matches_item_data)

            matches.append(matches_item)

        def _parse_top_match(
            data: object,
        ) -> None | PreviouslySeenMatchResource | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                top_match_type_0 = PreviouslySeenMatchResource.from_dict(data)

                return top_match_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviouslySeenMatchResource | Unset, data)

        top_match = _parse_top_match(d.pop("top_match", UNSET))

        previously_seen_check_result_attributes = cls(
            should_auto_publish=should_auto_publish,
            should_auto_request=should_auto_request,
            autopublish_threshold=autopublish_threshold,
            autorequest_threshold=autorequest_threshold,
            matches=matches,
            top_match=top_match,
        )

        previously_seen_check_result_attributes.additional_properties = d
        return previously_seen_check_result_attributes

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
