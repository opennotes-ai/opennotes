from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="FlashpointDetectionUpdateRequest")


@_attrs_define
class FlashpointDetectionUpdateRequest:
    """Request model for updating flashpoint detection setting.

    Attributes:
        enabled (bool): Whether to enable flashpoint detection for this community
    """

    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        enabled = self.enabled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "enabled": enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        enabled = d.pop("enabled")

        flashpoint_detection_update_request = cls(
            enabled=enabled,
        )

        return flashpoint_detection_update_request
