from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.agent_profile_data import AgentProfileData
    from ..models.request_variance_meta import RequestVarianceMeta


T = TypeVar("T", bound="DetailedAnalysisMeta")


@_attrs_define
class DetailedAnalysisMeta:
    """
    Attributes:
        count (int | Unset):  Default: 0.
        request_variance (RequestVarianceMeta | Unset):
        agents (list[AgentProfileData] | Unset):
    """

    count: int | Unset = 0
    request_variance: RequestVarianceMeta | Unset = UNSET
    agents: list[AgentProfileData] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        request_variance: dict[str, Any] | Unset = UNSET
        if not isinstance(self.request_variance, Unset):
            request_variance = self.request_variance.to_dict()

        agents: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.agents, Unset):
            agents = []
            for agents_item_data in self.agents:
                agents_item = agents_item_data.to_dict()
                agents.append(agents_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if count is not UNSET:
            field_dict["count"] = count
        if request_variance is not UNSET:
            field_dict["request_variance"] = request_variance
        if agents is not UNSET:
            field_dict["agents"] = agents

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.agent_profile_data import AgentProfileData
        from ..models.request_variance_meta import RequestVarianceMeta

        d = dict(src_dict)
        count = d.pop("count", UNSET)

        _request_variance = d.pop("request_variance", UNSET)
        request_variance: RequestVarianceMeta | Unset
        if isinstance(_request_variance, Unset):
            request_variance = UNSET
        else:
            request_variance = RequestVarianceMeta.from_dict(_request_variance)

        _agents = d.pop("agents", UNSET)
        agents: list[AgentProfileData] | Unset = UNSET
        if _agents is not UNSET:
            agents = []
            for agents_item_data in _agents:
                agents_item = AgentProfileData.from_dict(agents_item_data)

                agents.append(agents_item)

        detailed_analysis_meta = cls(
            count=count,
            request_variance=request_variance,
            agents=agents,
        )

        detailed_analysis_meta.additional_properties = d
        return detailed_analysis_meta

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
