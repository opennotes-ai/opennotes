from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.request_attributes_metadata_type_0 import (
        RequestAttributesMetadataType0,
    )


T = TypeVar("T", bound="RequestAttributes")


@_attrs_define
class RequestAttributes:
    """Request attributes for JSON:API resource.

    Attributes:
        request_id (str):
        requested_by (str):
        status (str | Unset):  Default: 'PENDING'.
        note_id (None | str | Unset):
        community_server_id (None | str | Unset):
        requested_at (datetime.datetime | None | Unset):
        created_at (datetime.datetime | None | Unset):
        updated_at (datetime.datetime | None | Unset):
        content (None | str | Unset):
        platform_message_id (None | str | Unset):
        metadata (None | RequestAttributesMetadataType0 | Unset):
        similarity_score (float | None | Unset):
        dataset_name (None | str | Unset):
        dataset_item_id (None | str | Unset):
    """

    request_id: str
    requested_by: str
    status: str | Unset = "PENDING"
    note_id: None | str | Unset = UNSET
    community_server_id: None | str | Unset = UNSET
    requested_at: datetime.datetime | None | Unset = UNSET
    created_at: datetime.datetime | None | Unset = UNSET
    updated_at: datetime.datetime | None | Unset = UNSET
    content: None | str | Unset = UNSET
    platform_message_id: None | str | Unset = UNSET
    metadata: None | RequestAttributesMetadataType0 | Unset = UNSET
    similarity_score: float | None | Unset = UNSET
    dataset_name: None | str | Unset = UNSET
    dataset_item_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.request_attributes_metadata_type_0 import (
            RequestAttributesMetadataType0,
        )

        request_id = self.request_id

        requested_by = self.requested_by

        status = self.status

        note_id: None | str | Unset
        if isinstance(self.note_id, Unset):
            note_id = UNSET
        else:
            note_id = self.note_id

        community_server_id: None | str | Unset
        if isinstance(self.community_server_id, Unset):
            community_server_id = UNSET
        else:
            community_server_id = self.community_server_id

        requested_at: None | str | Unset
        if isinstance(self.requested_at, Unset):
            requested_at = UNSET
        elif isinstance(self.requested_at, datetime.datetime):
            requested_at = self.requested_at.isoformat()
        else:
            requested_at = self.requested_at

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        updated_at: None | str | Unset
        if isinstance(self.updated_at, Unset):
            updated_at = UNSET
        elif isinstance(self.updated_at, datetime.datetime):
            updated_at = self.updated_at.isoformat()
        else:
            updated_at = self.updated_at

        content: None | str | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        else:
            content = self.content

        platform_message_id: None | str | Unset
        if isinstance(self.platform_message_id, Unset):
            platform_message_id = UNSET
        else:
            platform_message_id = self.platform_message_id

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, RequestAttributesMetadataType0):
            metadata = self.metadata.to_dict()
        else:
            metadata = self.metadata

        similarity_score: float | None | Unset
        if isinstance(self.similarity_score, Unset):
            similarity_score = UNSET
        else:
            similarity_score = self.similarity_score

        dataset_name: None | str | Unset
        if isinstance(self.dataset_name, Unset):
            dataset_name = UNSET
        else:
            dataset_name = self.dataset_name

        dataset_item_id: None | str | Unset
        if isinstance(self.dataset_item_id, Unset):
            dataset_item_id = UNSET
        else:
            dataset_item_id = self.dataset_item_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "request_id": request_id,
                "requested_by": requested_by,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status
        if note_id is not UNSET:
            field_dict["note_id"] = note_id
        if community_server_id is not UNSET:
            field_dict["community_server_id"] = community_server_id
        if requested_at is not UNSET:
            field_dict["requested_at"] = requested_at
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if updated_at is not UNSET:
            field_dict["updated_at"] = updated_at
        if content is not UNSET:
            field_dict["content"] = content
        if platform_message_id is not UNSET:
            field_dict["platform_message_id"] = platform_message_id
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if similarity_score is not UNSET:
            field_dict["similarity_score"] = similarity_score
        if dataset_name is not UNSET:
            field_dict["dataset_name"] = dataset_name
        if dataset_item_id is not UNSET:
            field_dict["dataset_item_id"] = dataset_item_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.request_attributes_metadata_type_0 import (
            RequestAttributesMetadataType0,
        )

        d = dict(src_dict)
        request_id = d.pop("request_id")

        requested_by = d.pop("requested_by")

        status = d.pop("status", UNSET)

        def _parse_note_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        note_id = _parse_note_id(d.pop("note_id", UNSET))

        def _parse_community_server_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        community_server_id = _parse_community_server_id(
            d.pop("community_server_id", UNSET)
        )

        def _parse_requested_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                requested_at_type_0 = isoparse(data)

                return requested_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        requested_at = _parse_requested_at(d.pop("requested_at", UNSET))

        def _parse_created_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_at_type_0 = isoparse(data)

                return created_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        created_at = _parse_created_at(d.pop("created_at", UNSET))

        def _parse_updated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                updated_at_type_0 = isoparse(data)

                return updated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        updated_at = _parse_updated_at(d.pop("updated_at", UNSET))

        def _parse_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_platform_message_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_message_id = _parse_platform_message_id(
            d.pop("platform_message_id", UNSET)
        )

        def _parse_metadata(
            data: object,
        ) -> None | RequestAttributesMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = RequestAttributesMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RequestAttributesMetadataType0 | Unset, data)

        metadata = _parse_metadata(d.pop("metadata", UNSET))

        def _parse_similarity_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        similarity_score = _parse_similarity_score(d.pop("similarity_score", UNSET))

        def _parse_dataset_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dataset_name = _parse_dataset_name(d.pop("dataset_name", UNSET))

        def _parse_dataset_item_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dataset_item_id = _parse_dataset_item_id(d.pop("dataset_item_id", UNSET))

        request_attributes = cls(
            request_id=request_id,
            requested_by=requested_by,
            status=status,
            note_id=note_id,
            community_server_id=community_server_id,
            requested_at=requested_at,
            created_at=created_at,
            updated_at=updated_at,
            content=content,
            platform_message_id=platform_message_id,
            metadata=metadata,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            dataset_item_id=dataset_item_id,
        )

        request_attributes.additional_properties = d
        return request_attributes

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
