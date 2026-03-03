from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="DetailedRatingData")


@_attrs_define
class DetailedRatingData:
    """
    Attributes:
        rater_agent_name (str):
        rater_agent_instance_id (str):
        helpfulness_level (str):
        created_at (datetime.datetime | None | Unset):
    """

    rater_agent_name: str
    rater_agent_instance_id: str
    helpfulness_level: str
    created_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rater_agent_name = self.rater_agent_name

        rater_agent_instance_id = self.rater_agent_instance_id

        helpfulness_level = self.helpfulness_level

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
                "rater_agent_name": rater_agent_name,
                "rater_agent_instance_id": rater_agent_instance_id,
                "helpfulness_level": helpfulness_level,
            }
        )
        if created_at is not UNSET:
            field_dict["created_at"] = created_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rater_agent_name = d.pop("rater_agent_name")

        rater_agent_instance_id = d.pop("rater_agent_instance_id")

        helpfulness_level = d.pop("helpfulness_level")

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

        detailed_rating_data = cls(
            rater_agent_name=rater_agent_name,
            rater_agent_instance_id=rater_agent_instance_id,
            helpfulness_level=helpfulness_level,
            created_at=created_at,
        )

        detailed_rating_data.additional_properties = d
        return detailed_rating_data

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
