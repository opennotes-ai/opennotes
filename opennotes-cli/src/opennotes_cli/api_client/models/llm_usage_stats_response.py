from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.llm_usage_stats_response_daily_requests import (
        LLMUsageStatsResponseDailyRequests,
    )
    from ..models.llm_usage_stats_response_daily_spend import (
        LLMUsageStatsResponseDailySpend,
    )
    from ..models.llm_usage_stats_response_daily_tokens import (
        LLMUsageStatsResponseDailyTokens,
    )
    from ..models.llm_usage_stats_response_monthly_requests import (
        LLMUsageStatsResponseMonthlyRequests,
    )
    from ..models.llm_usage_stats_response_monthly_spend import (
        LLMUsageStatsResponseMonthlySpend,
    )
    from ..models.llm_usage_stats_response_monthly_tokens import (
        LLMUsageStatsResponseMonthlyTokens,
    )


T = TypeVar("T", bound="LLMUsageStatsResponse")


@_attrs_define
class LLMUsageStatsResponse:
    """Schema for usage statistics response.

    Attributes:
        provider (str):
        daily_requests (LLMUsageStatsResponseDailyRequests):
        monthly_requests (LLMUsageStatsResponseMonthlyRequests):
        daily_tokens (LLMUsageStatsResponseDailyTokens):
        monthly_tokens (LLMUsageStatsResponseMonthlyTokens):
        daily_spend (LLMUsageStatsResponseDailySpend):
        monthly_spend (LLMUsageStatsResponseMonthlySpend):
        last_daily_reset (datetime.datetime | None):
        last_monthly_reset (datetime.datetime | None):
    """

    provider: str
    daily_requests: LLMUsageStatsResponseDailyRequests
    monthly_requests: LLMUsageStatsResponseMonthlyRequests
    daily_tokens: LLMUsageStatsResponseDailyTokens
    monthly_tokens: LLMUsageStatsResponseMonthlyTokens
    daily_spend: LLMUsageStatsResponseDailySpend
    monthly_spend: LLMUsageStatsResponseMonthlySpend
    last_daily_reset: datetime.datetime | None
    last_monthly_reset: datetime.datetime | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        provider = self.provider

        daily_requests = self.daily_requests.to_dict()

        monthly_requests = self.monthly_requests.to_dict()

        daily_tokens = self.daily_tokens.to_dict()

        monthly_tokens = self.monthly_tokens.to_dict()

        daily_spend = self.daily_spend.to_dict()

        monthly_spend = self.monthly_spend.to_dict()

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "provider": provider,
                "daily_requests": daily_requests,
                "monthly_requests": monthly_requests,
                "daily_tokens": daily_tokens,
                "monthly_tokens": monthly_tokens,
                "daily_spend": daily_spend,
                "monthly_spend": monthly_spend,
                "last_daily_reset": last_daily_reset,
                "last_monthly_reset": last_monthly_reset,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_usage_stats_response_daily_requests import (
            LLMUsageStatsResponseDailyRequests,
        )
        from ..models.llm_usage_stats_response_daily_spend import (
            LLMUsageStatsResponseDailySpend,
        )
        from ..models.llm_usage_stats_response_daily_tokens import (
            LLMUsageStatsResponseDailyTokens,
        )
        from ..models.llm_usage_stats_response_monthly_requests import (
            LLMUsageStatsResponseMonthlyRequests,
        )
        from ..models.llm_usage_stats_response_monthly_spend import (
            LLMUsageStatsResponseMonthlySpend,
        )
        from ..models.llm_usage_stats_response_monthly_tokens import (
            LLMUsageStatsResponseMonthlyTokens,
        )

        d = dict(src_dict)
        provider = d.pop("provider")

        daily_requests = LLMUsageStatsResponseDailyRequests.from_dict(
            d.pop("daily_requests")
        )

        monthly_requests = LLMUsageStatsResponseMonthlyRequests.from_dict(
            d.pop("monthly_requests")
        )

        daily_tokens = LLMUsageStatsResponseDailyTokens.from_dict(d.pop("daily_tokens"))

        monthly_tokens = LLMUsageStatsResponseMonthlyTokens.from_dict(
            d.pop("monthly_tokens")
        )

        daily_spend = LLMUsageStatsResponseDailySpend.from_dict(d.pop("daily_spend"))

        monthly_spend = LLMUsageStatsResponseMonthlySpend.from_dict(
            d.pop("monthly_spend")
        )

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

        llm_usage_stats_response = cls(
            provider=provider,
            daily_requests=daily_requests,
            monthly_requests=monthly_requests,
            daily_tokens=daily_tokens,
            monthly_tokens=monthly_tokens,
            daily_spend=daily_spend,
            monthly_spend=monthly_spend,
            last_daily_reset=last_daily_reset,
            last_monthly_reset=last_monthly_reset,
        )

        llm_usage_stats_response.additional_properties = d
        return llm_usage_stats_response

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
