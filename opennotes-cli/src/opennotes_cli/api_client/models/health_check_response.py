from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.health_check_response_components import HealthCheckResponseComponents


T = TypeVar("T", bound="HealthCheckResponse")


@_attrs_define
class HealthCheckResponse:
    """
    Attributes:
        status (str): Overall system status
        version (str): API version
        timestamp (float | Unset): Unix epoch timestamp
        environment (None | str | Unset): Environment name
        components (HealthCheckResponseComponents | Unset): Component statuses
        uptime_seconds (float | None | Unset): Server uptime in seconds
    """

    status: str
    version: str
    timestamp: float | Unset = UNSET
    environment: None | str | Unset = UNSET
    components: HealthCheckResponseComponents | Unset = UNSET
    uptime_seconds: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status

        version = self.version

        timestamp = self.timestamp

        environment: None | str | Unset
        if isinstance(self.environment, Unset):
            environment = UNSET
        else:
            environment = self.environment

        components: dict[str, Any] | Unset = UNSET
        if not isinstance(self.components, Unset):
            components = self.components.to_dict()

        uptime_seconds: float | None | Unset
        if isinstance(self.uptime_seconds, Unset):
            uptime_seconds = UNSET
        else:
            uptime_seconds = self.uptime_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
                "version": version,
            }
        )
        if timestamp is not UNSET:
            field_dict["timestamp"] = timestamp
        if environment is not UNSET:
            field_dict["environment"] = environment
        if components is not UNSET:
            field_dict["components"] = components
        if uptime_seconds is not UNSET:
            field_dict["uptime_seconds"] = uptime_seconds

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.health_check_response_components import (
            HealthCheckResponseComponents,
        )

        d = dict(src_dict)
        status = d.pop("status")

        version = d.pop("version")

        timestamp = d.pop("timestamp", UNSET)

        def _parse_environment(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        environment = _parse_environment(d.pop("environment", UNSET))

        _components = d.pop("components", UNSET)
        components: HealthCheckResponseComponents | Unset
        if isinstance(_components, Unset):
            components = UNSET
        else:
            components = HealthCheckResponseComponents.from_dict(_components)

        def _parse_uptime_seconds(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        uptime_seconds = _parse_uptime_seconds(d.pop("uptime_seconds", UNSET))

        health_check_response = cls(
            status=status,
            version=version,
            timestamp=timestamp,
            environment=environment,
            components=components,
            uptime_seconds=uptime_seconds,
        )

        health_check_response.additional_properties = d
        return health_check_response

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
