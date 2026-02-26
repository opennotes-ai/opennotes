from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="RemoveCommunityAdminResponse")


@_attrs_define
class RemoveCommunityAdminResponse:
    """Response schema for admin removal.

    Attributes:
        success (bool): Whether the operation succeeded
        message (str): Human-readable result message
        profile_id (UUID): Profile ID of the affected user
        previous_role (str): User's previous role
        new_role (str): User's new role
    """

    success: bool
    message: str
    profile_id: UUID
    previous_role: str
    new_role: str

    def to_dict(self) -> dict[str, Any]:
        success = self.success

        message = self.message

        profile_id = str(self.profile_id)

        previous_role = self.previous_role

        new_role = self.new_role

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "success": success,
                "message": message,
                "profile_id": profile_id,
                "previous_role": previous_role,
                "new_role": new_role,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        success = d.pop("success")

        message = d.pop("message")

        profile_id = UUID(d.pop("profile_id"))

        previous_role = d.pop("previous_role")

        new_role = d.pop("new_role")

        remove_community_admin_response = cls(
            success=success,
            message=message,
            profile_id=profile_id,
            previous_role=previous_role,
            new_role=new_role,
        )

        return remove_community_admin_response
