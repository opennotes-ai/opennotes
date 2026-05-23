from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FrameCompatResponse")


@_attrs_define
class FrameCompatResponse:
    """
    Attributes:
        can_iframe (bool):
        blocking_header (None | str | Unset):
        csp_frame_ancestors (None | str | Unset):
        has_archive (bool | Unset):  Default: False.
    """

    can_iframe: bool
    blocking_header: None | str | Unset = UNSET
    csp_frame_ancestors: None | str | Unset = UNSET
    has_archive: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        can_iframe = self.can_iframe

        blocking_header: None | str | Unset
        if isinstance(self.blocking_header, Unset):
            blocking_header = UNSET
        else:
            blocking_header = self.blocking_header

        csp_frame_ancestors: None | str | Unset
        if isinstance(self.csp_frame_ancestors, Unset):
            csp_frame_ancestors = UNSET
        else:
            csp_frame_ancestors = self.csp_frame_ancestors

        has_archive = self.has_archive

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "can_iframe": can_iframe,
            }
        )
        if blocking_header is not UNSET:
            field_dict["blocking_header"] = blocking_header
        if csp_frame_ancestors is not UNSET:
            field_dict["csp_frame_ancestors"] = csp_frame_ancestors
        if has_archive is not UNSET:
            field_dict["has_archive"] = has_archive

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        can_iframe = d.pop("can_iframe")

        def _parse_blocking_header(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        blocking_header = _parse_blocking_header(d.pop("blocking_header", UNSET))

        def _parse_csp_frame_ancestors(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        csp_frame_ancestors = _parse_csp_frame_ancestors(
            d.pop("csp_frame_ancestors", UNSET)
        )

        has_archive = d.pop("has_archive", UNSET)

        frame_compat_response = cls(
            can_iframe=can_iframe,
            blocking_header=blocking_header,
            csp_frame_ancestors=csp_frame_ancestors,
            has_archive=has_archive,
        )

        frame_compat_response.additional_properties = d
        return frame_compat_response

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
