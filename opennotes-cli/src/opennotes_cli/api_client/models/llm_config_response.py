from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.llm_config_response_settings import LLMConfigResponseSettings


T = TypeVar("T", bound="LLMConfigResponse")


@_attrs_define
class LLMConfigResponse:
    """Schema for LLM configuration response (excludes full API key).

    Attributes:
        id (UUID):
        community_server_id (UUID):
        provider (str):
        api_key_preview (str): Last 4 characters of API key
        enabled (bool):
        settings (LLMConfigResponseSettings):
        daily_request_limit (int | None):
        monthly_request_limit (int | None):
        daily_token_limit (int | None):
        monthly_token_limit (int | None):
        daily_spend_limit (float | None):
        monthly_spend_limit (float | None):
        current_daily_requests (int):
        current_monthly_requests (int):
        current_daily_tokens (int):
        current_monthly_tokens (int):
        current_daily_spend (float):
        current_monthly_spend (float):
        last_daily_reset (datetime.datetime | None):
        last_monthly_reset (datetime.datetime | None):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        created_by (None | UUID):
    """

    id: UUID
    community_server_id: UUID
    provider: str
    api_key_preview: str
    enabled: bool
    settings: LLMConfigResponseSettings
    daily_request_limit: int | None
    monthly_request_limit: int | None
    daily_token_limit: int | None
    monthly_token_limit: int | None
    daily_spend_limit: float | None
    monthly_spend_limit: float | None
    current_daily_requests: int
    current_monthly_requests: int
    current_daily_tokens: int
    current_monthly_tokens: int
    current_daily_spend: float
    current_monthly_spend: float
    last_daily_reset: datetime.datetime | None
    last_monthly_reset: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: None | UUID
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        community_server_id = str(self.community_server_id)

        provider = self.provider

        api_key_preview = self.api_key_preview

        enabled = self.enabled

        settings = self.settings.to_dict()

        daily_request_limit: int | None
        daily_request_limit = self.daily_request_limit

        monthly_request_limit: int | None
        monthly_request_limit = self.monthly_request_limit

        daily_token_limit: int | None
        daily_token_limit = self.daily_token_limit

        monthly_token_limit: int | None
        monthly_token_limit = self.monthly_token_limit

        daily_spend_limit: float | None
        daily_spend_limit = self.daily_spend_limit

        monthly_spend_limit: float | None
        monthly_spend_limit = self.monthly_spend_limit

        current_daily_requests = self.current_daily_requests

        current_monthly_requests = self.current_monthly_requests

        current_daily_tokens = self.current_daily_tokens

        current_monthly_tokens = self.current_monthly_tokens

        current_daily_spend = self.current_daily_spend

        current_monthly_spend = self.current_monthly_spend

        last_daily_reset: None | str
        if isinstance(self.last_daily_reset, datetime.datetime):
            last_daily_reset = self.last_daily_reset.isoformat()
        else:
            last_daily_reset = self.last_daily_reset

        last_monthly_reset: None | str
        if isinstance(self.last_monthly_reset, datetime.datetime):
            last_monthly_reset = self.last_monthly_reset.isoformat()
        else:
            last_monthly_reset = self.last_monthly_reset

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        created_by: None | str
        if isinstance(self.created_by, UUID):
            created_by = str(self.created_by)
        else:
            created_by = self.created_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "community_server_id": community_server_id,
                "provider": provider,
                "api_key_preview": api_key_preview,
                "enabled": enabled,
                "settings": settings,
                "daily_request_limit": daily_request_limit,
                "monthly_request_limit": monthly_request_limit,
                "daily_token_limit": daily_token_limit,
                "monthly_token_limit": monthly_token_limit,
                "daily_spend_limit": daily_spend_limit,
                "monthly_spend_limit": monthly_spend_limit,
                "current_daily_requests": current_daily_requests,
                "current_monthly_requests": current_monthly_requests,
                "current_daily_tokens": current_daily_tokens,
                "current_monthly_tokens": current_monthly_tokens,
                "current_daily_spend": current_daily_spend,
                "current_monthly_spend": current_monthly_spend,
                "last_daily_reset": last_daily_reset,
                "last_monthly_reset": last_monthly_reset,
                "created_at": created_at,
                "updated_at": updated_at,
                "created_by": created_by,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_config_response_settings import LLMConfigResponseSettings

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        community_server_id = UUID(d.pop("community_server_id"))

        provider = d.pop("provider")

        api_key_preview = d.pop("api_key_preview")

        enabled = d.pop("enabled")

        settings = LLMConfigResponseSettings.from_dict(d.pop("settings"))

        def _parse_daily_request_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        daily_request_limit = _parse_daily_request_limit(d.pop("daily_request_limit"))

        def _parse_monthly_request_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        monthly_request_limit = _parse_monthly_request_limit(
            d.pop("monthly_request_limit")
        )

        def _parse_daily_token_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        daily_token_limit = _parse_daily_token_limit(d.pop("daily_token_limit"))

        def _parse_monthly_token_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        monthly_token_limit = _parse_monthly_token_limit(d.pop("monthly_token_limit"))

        def _parse_daily_spend_limit(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        daily_spend_limit = _parse_daily_spend_limit(d.pop("daily_spend_limit"))

        def _parse_monthly_spend_limit(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        monthly_spend_limit = _parse_monthly_spend_limit(d.pop("monthly_spend_limit"))

        current_daily_requests = d.pop("current_daily_requests")

        current_monthly_requests = d.pop("current_monthly_requests")

        current_daily_tokens = d.pop("current_daily_tokens")

        current_monthly_tokens = d.pop("current_monthly_tokens")

        current_daily_spend = d.pop("current_daily_spend")

        current_monthly_spend = d.pop("current_monthly_spend")

        def _parse_last_daily_reset(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_daily_reset_type_0 = isoparse(data)

                return last_daily_reset_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_daily_reset = _parse_last_daily_reset(d.pop("last_daily_reset"))

        def _parse_last_monthly_reset(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_monthly_reset_type_0 = isoparse(data)

                return last_monthly_reset_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_monthly_reset = _parse_last_monthly_reset(d.pop("last_monthly_reset"))

        created_at = isoparse(d.pop("created_at"))

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_created_by(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                created_by_type_0 = UUID(data)

                return created_by_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        created_by = _parse_created_by(d.pop("created_by"))

        llm_config_response = cls(
            id=id,
            community_server_id=community_server_id,
            provider=provider,
            api_key_preview=api_key_preview,
            enabled=enabled,
            settings=settings,
            daily_request_limit=daily_request_limit,
            monthly_request_limit=monthly_request_limit,
            daily_token_limit=daily_token_limit,
            monthly_token_limit=monthly_token_limit,
            daily_spend_limit=daily_spend_limit,
            monthly_spend_limit=monthly_spend_limit,
            current_daily_requests=current_daily_requests,
            current_monthly_requests=current_monthly_requests,
            current_daily_tokens=current_daily_tokens,
            current_monthly_tokens=current_monthly_tokens,
            current_daily_spend=current_daily_spend,
            current_monthly_spend=current_monthly_spend,
            last_daily_reset=last_daily_reset,
            last_monthly_reset=last_monthly_reset,
            created_at=created_at,
            updated_at=updated_at,
            created_by=created_by,
        )

        llm_config_response.additional_properties = d
        return llm_config_response

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
