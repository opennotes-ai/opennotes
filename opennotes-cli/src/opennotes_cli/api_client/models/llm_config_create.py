from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.llm_config_create_provider import LLMConfigCreateProvider
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.llm_config_create_settings import LLMConfigCreateSettings


T = TypeVar("T", bound="LLMConfigCreate")


@_attrs_define
class LLMConfigCreate:
    """Schema for creating a new LLM configuration.

    Attributes:
        provider (LLMConfigCreateProvider):
        api_key (str): API key for the LLM provider
        enabled (bool | Unset): Whether this configuration is enabled Default: True.
        settings (LLMConfigCreateSettings | Unset): Provider-specific settings (model, temperature, etc.). Kept as
            dict[str, Any] - each LLM provider has different configuration options and parameters.
        daily_request_limit (int | None | Unset): Maximum daily API requests (None = unlimited)
        monthly_request_limit (int | None | Unset): Maximum monthly API requests (None = unlimited)
        daily_token_limit (int | None | Unset): Maximum daily tokens (None = unlimited)
        monthly_token_limit (int | None | Unset): Maximum monthly tokens (None = unlimited)
        daily_spend_limit (float | None | Unset): Maximum daily spending in USD (None = unlimited)
        monthly_spend_limit (float | None | Unset): Maximum monthly spending in USD (None = unlimited)
    """

    provider: LLMConfigCreateProvider
    api_key: str
    enabled: bool | Unset = True
    settings: LLMConfigCreateSettings | Unset = UNSET
    daily_request_limit: int | None | Unset = UNSET
    monthly_request_limit: int | None | Unset = UNSET
    daily_token_limit: int | None | Unset = UNSET
    monthly_token_limit: int | None | Unset = UNSET
    daily_spend_limit: float | None | Unset = UNSET
    monthly_spend_limit: float | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        provider = self.provider.value

        api_key = self.api_key

        enabled = self.enabled

        settings: dict[str, Any] | Unset = UNSET
        if not isinstance(self.settings, Unset):
            settings = self.settings.to_dict()

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

        field_dict.update(
            {
                "provider": provider,
                "api_key": api_key,
            }
        )
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
        from ..models.llm_config_create_settings import LLMConfigCreateSettings

        d = dict(src_dict)
        provider = LLMConfigCreateProvider(d.pop("provider"))

        api_key = d.pop("api_key")

        enabled = d.pop("enabled", UNSET)

        _settings = d.pop("settings", UNSET)
        settings: LLMConfigCreateSettings | Unset
        if isinstance(_settings, Unset):
            settings = UNSET
        else:
            settings = LLMConfigCreateSettings.from_dict(_settings)

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

        llm_config_create = cls(
            provider=provider,
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

        return llm_config_create
