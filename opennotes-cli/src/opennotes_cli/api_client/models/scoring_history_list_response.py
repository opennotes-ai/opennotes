from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.scoring_history_entry_resource import ScoringHistoryEntryResource
    from ..models.scoring_history_list_response_jsonapi import (
        ScoringHistoryListResponseJsonapi,
    )
    from ..models.scoring_history_list_response_meta_type_0 import (
        ScoringHistoryListResponseMetaType0,
    )


T = TypeVar("T", bound="ScoringHistoryListResponse")


@_attrs_define
class ScoringHistoryListResponse:
    """
    Attributes:
        data (list[ScoringHistoryEntryResource]):
        jsonapi (ScoringHistoryListResponseJsonapi | Unset):
        meta (None | ScoringHistoryListResponseMetaType0 | Unset):
    """

    data: list[ScoringHistoryEntryResource]
    jsonapi: ScoringHistoryListResponseJsonapi | Unset = UNSET
    meta: None | ScoringHistoryListResponseMetaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.scoring_history_list_response_meta_type_0 import (
            ScoringHistoryListResponseMetaType0,
        )

        data = []
        for data_item_data in self.data:
            data_item = data_item_data.to_dict()
            data.append(data_item)

        jsonapi: dict[str, Any] | Unset = UNSET
        if not isinstance(self.jsonapi, Unset):
            jsonapi = self.jsonapi.to_dict()

        meta: dict[str, Any] | None | Unset
        if isinstance(self.meta, Unset):
            meta = UNSET
        elif isinstance(self.meta, ScoringHistoryListResponseMetaType0):
            meta = self.meta.to_dict()
        else:
            meta = self.meta

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )
        if jsonapi is not UNSET:
            field_dict["jsonapi"] = jsonapi
        if meta is not UNSET:
            field_dict["meta"] = meta

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.scoring_history_entry_resource import ScoringHistoryEntryResource
        from ..models.scoring_history_list_response_jsonapi import (
            ScoringHistoryListResponseJsonapi,
        )
        from ..models.scoring_history_list_response_meta_type_0 import (
            ScoringHistoryListResponseMetaType0,
        )

        d = dict(src_dict)
        data = []
        _data = d.pop("data")
        for data_item_data in _data:
            data_item = ScoringHistoryEntryResource.from_dict(data_item_data)

            data.append(data_item)

        _jsonapi = d.pop("jsonapi", UNSET)
        jsonapi: ScoringHistoryListResponseJsonapi | Unset
        if isinstance(_jsonapi, Unset):
            jsonapi = UNSET
        else:
            jsonapi = ScoringHistoryListResponseJsonapi.from_dict(_jsonapi)

        def _parse_meta(
            data: object,
        ) -> None | ScoringHistoryListResponseMetaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                meta_type_0 = ScoringHistoryListResponseMetaType0.from_dict(data)

                return meta_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ScoringHistoryListResponseMetaType0 | Unset, data)

        meta = _parse_meta(d.pop("meta", UNSET))

        scoring_history_list_response = cls(
            data=data,
            jsonapi=jsonapi,
            meta=meta,
        )

        scoring_history_list_response.additional_properties = d
        return scoring_history_list_response

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
