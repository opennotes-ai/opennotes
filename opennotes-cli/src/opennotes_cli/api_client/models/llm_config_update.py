from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.llm_config_update_settings_type_0 import LLMConfigUpdateSettingsType0


T = TypeVar("T", bound="LLMConfigUpdate")


@_attrs_define
class LLMConfigUpdate:
    """Schema for updating an existing LLM configuration.

    Attributes:
        api_key (None | str | Unset):
        enabled (bool | None | Unset):
        settings (LLMConfigUpdateSettingsType0 | None | Unset):
        daily_request_limit (int | None | Unset):
        monthly_request_limit (int | None | Unset):
        daily_token_limit (int | None | Unset):
        monthly_token_limit (int | None | Unset):
        daily_spend_limit (float | None | Unset):
        monthly_spend_limit (float | None | Unset):
    """

    api_key: None | str | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    settings: LLMConfigUpdateSettingsType0 | None | Unset = UNSET
    daily_request_limit: int | None | Unset = UNSET
    monthly_request_limit: int | None | Unset = UNSET
    daily_token_limit: int | None | Unset = UNSET
    monthly_token_limit: int | None | Unset = UNSET
    daily_spend_limit: float | None | Unset = UNSET
    monthly_spend_limit: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.llm_config_update_settings_type_0 import (
            LLMConfigUpdateSettingsType0,
        )

        api_key: None | str | Unset
        if isinstance(self.api_key, Unset):
            api_key = UNSET
        else:
            api_key = self.api_key

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        settings: dict[str, Any] | None | Unset
        if isinstance(self.settings, Unset):
            settings = UNSET
        elif isinstance(self.settings, LLMConfigUpdateSettingsType0):
            settings = self.settings.to_dict()
        else:
            settings = self.settings

        daily_request_limit: int | None | Unset
        if isinstance(self.daily_request_limit, Unset):
            daily_request_limit = UNSET
        else:
            daily_request_limit = self.daily_request_limit

        monthly_request_limit: int | None | Unset
        if isinstance(self.monthly_request_limit, Unset):
            monthly_request_limit = UNSET
        else:
            monthly_request_limit = self.monthly_request_limit

        daily_token_limit: int | None | Unset
        if isinstance(self.daily_token_limit, Unset):
            daily_token_limit = UNSET
        else:
            daily_token_limit = self.daily_token_limit

        monthly_token_limit: int | None | Unset
        if isinstance(self.monthly_token_limit, Unset):
            monthly_token_limit = UNSET
        else:
            monthly_token_limit = self.monthly_token_limit

        daily_spend_limit: float | None | Unset
        if isinstance(self.daily_spend_limit, Unset):
            daily_spend_limit = UNSET
        else:
            daily_spend_limit = self.daily_spend_limit

        monthly_spend_limit: float | None | Unset
        if isinstance(self.monthly_spend_limit, Unset):
            monthly_spend_limit = UNSET
        else:
            monthly_spend_limit = self.monthly_spend_limit

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if api_key is not UNSET:
            field_dict["api_key"] = api_key
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if settings is not UNSET:
            field_dict["settings"] = settings
        if daily_request_limit is not UNSET:
            field_dict["daily_request_limit"] = daily_request_limit
        if monthly_request_limit is not UNSET:
            field_dict["monthly_request_limit"] = monthly_request_limit
        if daily_token_limit is not UNSET:
            field_dict["daily_token_limit"] = daily_token_limit
        if monthly_token_limit is not UNSET:
            field_dict["monthly_token_limit"] = monthly_token_limit
        if daily_spend_limit is not UNSET:
            field_dict["daily_spend_limit"] = daily_spend_limit
        if monthly_spend_limit is not UNSET:
            field_dict["monthly_spend_limit"] = monthly_spend_limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_config_update_settings_type_0 import (
            LLMConfigUpdateSettingsType0,
        )

        d = dict(src_dict)

        def _parse_api_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        api_key = _parse_api_key(d.pop("api_key", UNSET))

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        def _parse_settings(
            data: object,
        ) -> LLMConfigUpdateSettingsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                settings_type_0 = LLMConfigUpdateSettingsType0.from_dict(data)

                return settings_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LLMConfigUpdateSettingsType0 | None | Unset, data)

        settings = _parse_settings(d.pop("settings", UNSET))

        def _parse_daily_request_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        daily_request_limit = _parse_daily_request_limit(
            d.pop("daily_request_limit", UNSET)
        )

        def _parse_monthly_request_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        monthly_request_limit = _parse_monthly_request_limit(
            d.pop("monthly_request_limit", UNSET)
        )

        def _parse_daily_token_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        daily_token_limit = _parse_daily_token_limit(d.pop("daily_token_limit", UNSET))

        def _parse_monthly_token_limit(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        monthly_token_limit = _parse_monthly_token_limit(
            d.pop("monthly_token_limit", UNSET)
        )

        def _parse_daily_spend_limit(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        daily_spend_limit = _parse_daily_spend_limit(d.pop("daily_spend_limit", UNSET))

        def _parse_monthly_spend_limit(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        monthly_spend_limit = _parse_monthly_spend_limit(
            d.pop("monthly_spend_limit", UNSET)
        )

        llm_config_update = cls(
            api_key=api_key,
            enabled=enabled,
            settings=settings,
            daily_request_limit=daily_request_limit,
            monthly_request_limit=monthly_request_limit,
            daily_token_limit=daily_token_limit,
            monthly_token_limit=monthly_token_limit,
            daily_spend_limit=daily_spend_limit,
            monthly_spend_limit=monthly_spend_limit,
        )

        return llm_config_update
