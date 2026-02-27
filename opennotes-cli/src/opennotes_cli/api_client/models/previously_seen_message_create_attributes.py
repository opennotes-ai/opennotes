from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.previously_seen_message_create_attributes_extra_metadata_type_0 import (
        PreviouslySeenMessageCreateAttributesExtraMetadataType0,
    )


T = TypeVar("T", bound="PreviouslySeenMessageCreateAttributes")


@_attrs_define
class PreviouslySeenMessageCreateAttributes:
    """Attributes for creating a previously seen message via JSON:API.

    Attributes:
        community_server_id (str): Community server UUID
        original_message_id (str): Platform-specific message ID
        published_note_id (str): Note ID that was published for this message
        embedding (list[float] | None | Unset): Vector embedding for semantic similarity search (1536 dimensions)
        embedding_provider (None | str | Unset): LLM provider used for embedding generation
        embedding_model (None | str | Unset): Model name used for embedding generation
        extra_metadata (None | PreviouslySeenMessageCreateAttributesExtraMetadataType0 | Unset): Additional context
            metadata
    """

    community_server_id: str
    original_message_id: str
    published_note_id: str
    embedding: list[float] | None | Unset = UNSET
    embedding_provider: None | str | Unset = UNSET
    embedding_model: None | str | Unset = UNSET
    extra_metadata: (
        None | PreviouslySeenMessageCreateAttributesExtraMetadataType0 | Unset
    ) = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.previously_seen_message_create_attributes_extra_metadata_type_0 import (
            PreviouslySeenMessageCreateAttributesExtraMetadataType0,
        )

        community_server_id = self.community_server_id

        original_message_id = self.original_message_id

        published_note_id = self.published_note_id

        embedding: list[float] | None | Unset
        if isinstance(self.embedding, Unset):
            embedding = UNSET
        elif isinstance(self.embedding, list):
            embedding = self.embedding

        else:
            embedding = self.embedding

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
            self.extra_metadata, PreviouslySeenMessageCreateAttributesExtraMetadataType0
        ):
            extra_metadata = self.extra_metadata.to_dict()
        else:
            extra_metadata = self.extra_metadata

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "community_server_id": community_server_id,
                "original_message_id": original_message_id,
                "published_note_id": published_note_id,
            }
        )
        if embedding is not UNSET:
            field_dict["embedding"] = embedding
        if embedding_provider is not UNSET:
            field_dict["embedding_provider"] = embedding_provider
        if embedding_model is not UNSET:
            field_dict["embedding_model"] = embedding_model
        if extra_metadata is not UNSET:
            field_dict["extra_metadata"] = extra_metadata

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.previously_seen_message_create_attributes_extra_metadata_type_0 import (
            PreviouslySeenMessageCreateAttributesExtraMetadataType0,
        )

        d = dict(src_dict)
        community_server_id = d.pop("community_server_id")

        original_message_id = d.pop("original_message_id")

        published_note_id = d.pop("published_note_id")

        def _parse_embedding(data: object) -> list[float] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                embedding_type_0 = cast(list[float], data)

                return embedding_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[float] | None | Unset, data)

        embedding = _parse_embedding(d.pop("embedding", UNSET))

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
        ) -> None | PreviouslySeenMessageCreateAttributesExtraMetadataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extra_metadata_type_0 = (
                    PreviouslySeenMessageCreateAttributesExtraMetadataType0.from_dict(
                        data
                    )
                )

                return extra_metadata_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None | PreviouslySeenMessageCreateAttributesExtraMetadataType0 | Unset,
                data,
            )

        extra_metadata = _parse_extra_metadata(d.pop("extra_metadata", UNSET))

        previously_seen_message_create_attributes = cls(
            community_server_id=community_server_id,
            original_message_id=original_message_id,
            published_note_id=published_note_id,
            embedding=embedding,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            extra_metadata=extra_metadata,
        )

        return previously_seen_message_create_attributes
