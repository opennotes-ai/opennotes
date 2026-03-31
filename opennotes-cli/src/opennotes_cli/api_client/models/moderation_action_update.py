from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.action_state import ActionState
from ..types import UNSET, Unset

T = TypeVar("T", bound="ModerationActionUpdate")


@_attrs_define
class ModerationActionUpdate:
    """
    Attributes:
        action_state (ActionState):
        platform_action_id (None | str | Unset):
        scan_exempt_content_hash (None | str | Unset):
        overturned_reason (None | str | Unset):
    """

    action_state: ActionState
    platform_action_id: None | str | Unset = UNSET
    scan_exempt_content_hash: None | str | Unset = UNSET
    overturned_reason: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        action_state = self.action_state.value

        platform_action_id: None | str | Unset
        if isinstance(self.platform_action_id, Unset):
            platform_action_id = UNSET
        else:
            platform_action_id = self.platform_action_id

        scan_exempt_content_hash: None | str | Unset
        if isinstance(self.scan_exempt_content_hash, Unset):
            scan_exempt_content_hash = UNSET
        else:
            scan_exempt_content_hash = self.scan_exempt_content_hash

        overturned_reason: None | str | Unset
        if isinstance(self.overturned_reason, Unset):
            overturned_reason = UNSET
        else:
            overturned_reason = self.overturned_reason

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "action_state": action_state,
            }
        )
        if platform_action_id is not UNSET:
            field_dict["platform_action_id"] = platform_action_id
        if scan_exempt_content_hash is not UNSET:
            field_dict["scan_exempt_content_hash"] = scan_exempt_content_hash
        if overturned_reason is not UNSET:
            field_dict["overturned_reason"] = overturned_reason

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        action_state = ActionState(d.pop("action_state"))

        def _parse_platform_action_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_action_id = _parse_platform_action_id(
            d.pop("platform_action_id", UNSET)
        )

        def _parse_scan_exempt_content_hash(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        scan_exempt_content_hash = _parse_scan_exempt_content_hash(
            d.pop("scan_exempt_content_hash", UNSET)
        )

        def _parse_overturned_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        overturned_reason = _parse_overturned_reason(d.pop("overturned_reason", UNSET))

        moderation_action_update = cls(
            action_state=action_state,
            platform_action_id=platform_action_id,
            scan_exempt_content_hash=scan_exempt_content_hash,
            overturned_reason=overturned_reason,
        )

        return moderation_action_update
