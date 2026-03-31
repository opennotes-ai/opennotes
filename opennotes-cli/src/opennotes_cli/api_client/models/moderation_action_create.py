from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define

from ..models.action_state import ActionState
from ..models.action_tier import ActionTier
from ..models.action_type import ActionType
from ..models.review_group import ReviewGroup
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.moderation_action_create_classifier_evidence import (
        ModerationActionCreateClassifierEvidence,
    )


T = TypeVar("T", bound="ModerationActionCreate")


@_attrs_define
class ModerationActionCreate:
    """
    Attributes:
        request_id (UUID):
        community_server_id (UUID):
        action_type (ActionType):
        action_tier (ActionTier):
        classifier_evidence (ModerationActionCreateClassifierEvidence):
        review_group (ReviewGroup):
        note_id (None | Unset | UUID):
        action_state (ActionState | Unset):
    """

    request_id: UUID
    community_server_id: UUID
    action_type: ActionType
    action_tier: ActionTier
    classifier_evidence: ModerationActionCreateClassifierEvidence
    review_group: ReviewGroup
    note_id: None | Unset | UUID = UNSET
    action_state: ActionState | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        request_id = str(self.request_id)

        community_server_id = str(self.community_server_id)

        action_type = self.action_type.value

        action_tier = self.action_tier.value

        classifier_evidence = self.classifier_evidence.to_dict()

        review_group = self.review_group.value

        note_id: None | str | Unset
        if isinstance(self.note_id, Unset):
            note_id = UNSET
        elif isinstance(self.note_id, UUID):
            note_id = str(self.note_id)
        else:
            note_id = self.note_id

        action_state: str | Unset = UNSET
        if not isinstance(self.action_state, Unset):
            action_state = self.action_state.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "request_id": request_id,
                "community_server_id": community_server_id,
                "action_type": action_type,
                "action_tier": action_tier,
                "classifier_evidence": classifier_evidence,
                "review_group": review_group,
            }
        )
        if note_id is not UNSET:
            field_dict["note_id"] = note_id
        if action_state is not UNSET:
            field_dict["action_state"] = action_state

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.moderation_action_create_classifier_evidence import (
            ModerationActionCreateClassifierEvidence,
        )

        d = dict(src_dict)
        request_id = UUID(d.pop("request_id"))

        community_server_id = UUID(d.pop("community_server_id"))

        action_type = ActionType(d.pop("action_type"))

        action_tier = ActionTier(d.pop("action_tier"))

        classifier_evidence = ModerationActionCreateClassifierEvidence.from_dict(
            d.pop("classifier_evidence")
        )

        review_group = ReviewGroup(d.pop("review_group"))

        def _parse_note_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                note_id_type_0 = UUID(data)

                return note_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        note_id = _parse_note_id(d.pop("note_id", UNSET))

        _action_state = d.pop("action_state", UNSET)
        action_state: ActionState | Unset
        if isinstance(_action_state, Unset):
            action_state = UNSET
        else:
            action_state = ActionState(_action_state)

        moderation_action_create = cls(
            request_id=request_id,
            community_server_id=community_server_id,
            action_type=action_type,
            action_tier=action_tier,
            classifier_evidence=classifier_evidence,
            review_group=review_group,
            note_id=note_id,
            action_state=action_state,
        )

        return moderation_action_create
