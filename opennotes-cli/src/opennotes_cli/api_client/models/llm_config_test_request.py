from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..models.llm_config_test_request_provider import LLMConfigTestRequestProvider
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.llm_config_test_request_settings import LLMConfigTestRequestSettings


T = TypeVar("T", bound="LLMConfigTestRequest")


@_attrs_define
class LLMConfigTestRequest:
    """Schema for testing an LLM configuration.

    Attributes:
        provider (LLMConfigTestRequestProvider):
        api_key (str):
        settings (LLMConfigTestRequestSettings | Unset):
    """

    provider: LLMConfigTestRequestProvider
    api_key: str
    settings: LLMConfigTestRequestSettings | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        provider = self.provider.value

        api_key = self.api_key

        settings: dict[str, Any] | Unset = UNSET
        if not isinstance(self.settings, Unset):
            settings = self.settings.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "provider": provider,
                "api_key": api_key,
            }
        )
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_config_test_request_settings import (
            LLMConfigTestRequestSettings,
        )

        d = dict(src_dict)
        provider = LLMConfigTestRequestProvider(d.pop("provider"))

        api_key = d.pop("api_key")

        _settings = d.pop("settings", UNSET)
        settings: LLMConfigTestRequestSettings | Unset
        if isinstance(_settings, Unset):
            settings = UNSET
        else:
            settings = LLMConfigTestRequestSettings.from_dict(_settings)

        llm_config_test_request = cls(
            provider=provider,
            api_key=api_key,
            settings=settings,
        )

        return llm_config_test_request
