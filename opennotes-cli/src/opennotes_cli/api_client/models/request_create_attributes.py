from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.request_create_attributes_metadata_type_0 import (
        RequestCreateAttributesMetadataType0,
    )


T = TypeVar("T", bound="RequestCreateAttributes")


@_attrs_define
class RequestCreateAttributes:
    """Attributes for creating a request via JSON:API.

    Attributes:
        request_id (str): Unique request identifier
        requested_by (str): Requester's participant ID
        community_server_id (str): Community server ID (Discord guild ID, subreddit, etc.)
        original_message_content (None | str | Unset): Original message content
        platform_message_id (None | str | Unset): Platform message ID
        platform_channel_id (None | str | Unset): Platform channel ID
        platform_author_id (None | str | Unset): Platform author ID
        platform_timestamp (datetime.datetime | None | Unset): Platform message timestamp
        metadata (None | RequestCreateAttributesMetadataType0 | Unset): Request metadata
        similarity_score (float | None | Unset): Match similarity score
        dataset_name (None | str | Unset): Source dataset name
        dataset_item_id (None | str | Unset): Fact-check item ID
    """

    request_id: str
    requested_by: str
    community_server_id: str
    original_message_content: None | str | Unset = UNSET
    platform_message_id: None | str | Unset = UNSET
    platform_channel_id: None | str | Unset = UNSET
    platform_author_id: None | str | Unset = UNSET
    platform_timestamp: datetime.datetime | None | Unset = UNSET
    metadata: None | RequestCreateAttributesMetadataType0 | Unset = UNSET
    similarity_score: float | None | Unset = UNSET
    dataset_name: None | str | Unset = UNSET
    dataset_item_id: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.request_create_attributes_metadata_type_0 import (
            RequestCreateAttributesMetadataType0,
        )

        request_id = self.request_id

        requested_by = self.requested_by

        community_server_id = self.community_server_id

        original_message_content: None | str | Unset
        if isinstance(self.original_message_content, Unset):
            original_message_content = UNSET
        else:
            original_message_content = self.original_message_content

        platform_message_id: None | str | Unset
        if isinstance(self.platform_message_id, Unset):
            platform_message_id = UNSET
        else:
            platform_message_id = self.platform_message_id

        platform_channel_id: None | str | Unset
        if isinstance(self.platform_channel_id, Unset):
            platform_channel_id = UNSET
        else:
            platform_channel_id = self.platform_channel_id

        platform_author_id: None | str | Unset
        if isinstance(self.platform_author_id, Unset):
            platform_author_id = UNSET
        else:
            platform_author_id = self.platform_author_id

        platform_timestamp: None | str | Unset
        if isinstance(self.platform_timestamp, Unset):
            platform_timestamp = UNSET
        elif isinstance(self.platform_timestamp, datetime.datetime):
            platform_timestamp = self.platform_timestamp.isoformat()
        else:
            platform_timestamp = self.platform_timestamp

        metadata: dict[str, Any] | None | Unset
        if isinstance(self.metadata, Unset):
            metadata = UNSET
        elif isinstance(self.metadata, RequestCreateAttributesMetadataType0):
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

        field_dict.update(
            {
                "request_id": request_id,
                "requested_by": requested_by,
                "community_server_id": community_server_id,
            }
        )
        if original_message_content is not UNSET:
            field_dict["original_message_content"] = original_message_content
        if platform_message_id is not UNSET:
            field_dict["platform_message_id"] = platform_message_id
        if platform_channel_id is not UNSET:
            field_dict["platform_channel_id"] = platform_channel_id
        if platform_author_id is not UNSET:
            field_dict["platform_author_id"] = platform_author_id
        if platform_timestamp is not UNSET:
            field_dict["platform_timestamp"] = platform_timestamp
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
        from ..models.request_create_attributes_metadata_type_0 import (
            RequestCreateAttributesMetadataType0,
        )

        d = dict(src_dict)
        request_id = d.pop("request_id")

        requested_by = d.pop("requested_by")

        community_server_id = d.pop("community_server_id")

        def _parse_original_message_content(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        original_message_content = _parse_original_message_content(
            d.pop("original_message_content", UNSET)
        )

        def _parse_platform_message_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_message_id = _parse_platform_message_id(
            d.pop("platform_message_id", UNSET)
        )

        def _parse_platform_channel_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_channel_id = _parse_platform_channel_id(
            d.pop("platform_channel_id", UNSET)
        )

        def _parse_platform_author_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        platform_author_id = _parse_platform_author_id(
            d.pop("platform_author_id", UNSET)
        )

        def _parse_platform_timestamp(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                platform_timestamp_type_0 = isoparse(data)

                return platform_timestamp_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        platform_timestamp = _parse_platform_timestamp(
            d.pop("platform_timestamp", UNSET)
        )

        def _parse_metadata(
            data: object,
        ) -> None | RequestCreateAttributesMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                metadata_type_0 = RequestCreateAttributesMetadataType0.from_dict(data)

                return metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | RequestCreateAttributesMetadataType0 | Unset, data)

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

        request_create_attributes = cls(
            request_id=request_id,
            requested_by=requested_by,
            community_server_id=community_server_id,
            original_message_content=original_message_content,
            platform_message_id=platform_message_id,
            platform_channel_id=platform_channel_id,
            platform_author_id=platform_author_id,
            platform_timestamp=platform_timestamp,
            metadata=metadata,
            similarity_score=similarity_score,
            dataset_name=dataset_name,
            dataset_item_id=dataset_item_id,
        )

        return request_create_attributes
