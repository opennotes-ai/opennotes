from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RaterFactorData")


@_attrs_define
class RaterFactorData:
    """
    Attributes:
        rater_id (str):
        agent_name (None | str):
        personality (None | str):
        intercept (float | Unset):  Default: 0.0.
        factor1 (float | Unset):  Default: 0.0.
    """

    rater_id: str
    agent_name: None | str
    personality: None | str
    intercept: float | Unset = 0.0
    factor1: float | Unset = 0.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rater_id = self.rater_id

        agent_name: None | str
        agent_name = self.agent_name

        personality: None | str
        personality = self.personality

        intercept = self.intercept

        factor1 = self.factor1

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rater_id": rater_id,
                "agent_name": agent_name,
                "personality": personality,
            }
        )
        if intercept is not UNSET:
            field_dict["intercept"] = intercept
        if factor1 is not UNSET:
            field_dict["factor1"] = factor1

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rater_id = d.pop("rater_id")

        def _parse_agent_name(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        agent_name = _parse_agent_name(d.pop("agent_name"))

        def _parse_personality(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        personality = _parse_personality(d.pop("personality"))

        intercept = d.pop("intercept", UNSET)

        factor1 = d.pop("factor1", UNSET)

        rater_factor_data = cls(
            rater_id=rater_id,
            agent_name=agent_name,
            personality=personality,
            intercept=intercept,
            factor1=factor1,
        )

        rater_factor_data.additional_properties = d
        return rater_factor_data

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
