from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previously_seen_message_attributes_extra_metadata_type_0 import (
        PreviouslySeenMessageAttributesExtraMetadataType0,
    )


T = TypeVar("T", bound="PreviouslySeenMessageAttributes")


@_attrs_define
class PreviouslySeenMessageAttributes:
    """Previously seen message attributes for JSON:API resource.

    Attributes:
        community_server_id (str):
        original_message_id (str):
        published_note_id (str):
        embedding_provider (None | str | Unset):
        embedding_model (None | str | Unset):
        extra_metadata (None | PreviouslySeenMessageAttributesExtraMetadataType0 | Unset):
        created_at (datetime.datetime | None | Unset):
    """

    community_server_id: str
    original_message_id: str
    published_note_id: str
    embedding_provider: None | str | Unset = UNSET
    embedding_model: None | str | Unset = UNSET
    extra_metadata: None | PreviouslySeenMessageAttributesExtraMetadataType0 | Unset = (
        UNSET
    )
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.previously_seen_message_attributes_extra_metadata_type_0 import (
            PreviouslySeenMessageAttributesExtraMetadataType0,
        )

        community_server_id = self.community_server_id

        original_message_id = self.original_message_id

        published_note_id = self.published_note_id

        embedding_provider: None | str | Unset
        if isinstance(self.embedding_provider, Unset):
            embedding_provider = UNSET
        else:
            embedding_provider = self.embedding_provider

        embedding_model: None | str | Unset
        if isinstance(self.embedding_model, Unset):
            embedding_model = UNSET
        else:
            embedding_model = self.embedding_model

        extra_metadata: dict[str, Any] | None | Unset
        if isinstance(self.extra_metadata, Unset):
            extra_metadata = UNSET
        elif isinstance(
            self.extra_metadata, PreviouslySeenMessageAttributesExtraMetadataType0
        ):
            extra_metadata = self.extra_metadata.to_dict()
        else:
            extra_metadata = self.extra_metadata

        created_at: None | str | Unset
        if isinstance(self.created_at, Unset):
            created_at = UNSET
        elif isinstance(self.created_at, datetime.datetime):
            created_at = self.created_at.isoformat()
        else:
            created_at = self.created_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "community_server_id": community_server_id,
                "original_message_id": original_message_id,
                "published_note_id": published_note_id,
            }
        )
        if embedding_provider is not UNSET:
            field_dict["embedding_provider"] = embedding_provider
        if embedding_model is not UNSET:
            field_dict["embedding_model"] = embedding_model
        if extra_metadata is not UNSET:
            field_dict["extra_metadata"] = extra_metadata
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previously_seen_message_attributes_extra_metadata_type_0 import (
            PreviouslySeenMessageAttributesExtraMetadataType0,
        )

        d = dict(src_dict)
        community_server_id = d.pop("community_server_id")

        original_message_id = d.pop("original_message_id")

        published_note_id = d.pop("published_note_id")

        def _parse_embedding_provider(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        embedding_provider = _parse_embedding_provider(
            d.pop("embedding_provider", UNSET)
        )

        def _parse_embedding_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        embedding_model = _parse_embedding_model(d.pop("embedding_model", UNSET))

        def _parse_extra_metadata(
            data: object,
        ) -> None | PreviouslySeenMessageAttributesExtraMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extra_metadata_type_0 = (
                    PreviouslySeenMessageAttributesExtraMetadataType0.from_dict(data)
                )

                return extra_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | PreviouslySeenMessageAttributesExtraMetadataType0 | Unset, data
            )

        extra_metadata = _parse_extra_metadata(d.pop("extra_metadata", UNSET))

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

        previously_seen_message_attributes = cls(
            community_server_id=community_server_id,
            original_message_id=original_message_id,
            published_note_id=published_note_id,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            extra_metadata=extra_metadata,
            created_at=created_at,
        )

        previously_seen_message_attributes.additional_properties = d
        return previously_seen_message_attributes

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
