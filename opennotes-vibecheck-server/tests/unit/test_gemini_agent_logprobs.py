"""Unit tests for Gemini logprob settings and helper extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse

from src.config import Settings
from src.services.gemini_agent import (
    build_agent,
    extract_google_logprobs,
)


class _Out(BaseModel):
    text: str


@dataclass
class _FakeResult:
    response: ModelResponse


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _result_with_provider_details(provider_details: dict[str, Any] | None) -> _FakeResult:
    response = ModelResponse(parts=(), provider_details=provider_details)
    return _FakeResult(response=response)


def test_build_agent_default_does_not_set_logprob_model_settings(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(
            settings,
            output_type=_Out,
            system_prompt="ignored",
        )
        _, kwargs = mock_agent_cls.call_args
        assert "model_settings" not in kwargs


def test_build_agent_with_logprobs_true_passes_google_logprobs_settings(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(settings, output_type=_Out, logprobs=True)
        _, kwargs = mock_agent_cls.call_args
        model_settings = kwargs.get("model_settings")
        assert model_settings is not None
        assert model_settings.get("google_logprobs") is True


def test_build_agent_with_top_logprobs_adds_google_top_logprobs(settings: Settings) -> None:
    with patch("src.services.gemini_agent.Agent") as mock_agent_cls:
        mock_agent_cls.return_value = MagicMock()
        build_agent(settings, output_type=_Out, logprobs=True, top_logprobs=4)
        _, kwargs = mock_agent_cls.call_args
        model_settings = kwargs.get("model_settings")
        assert model_settings is not None
        assert model_settings["google_logprobs"] is True
        assert model_settings["google_top_logprobs"] == 4


def test_extract_google_logprobs_returns_none_when_provider_details_missing() -> None:
    result = _result_with_provider_details(None)
    assert extract_google_logprobs(result) is None


def test_extract_google_logprobs_returns_data_when_present() -> None:
    expected = {
        "logprobs": {"token_count": 3},
        "avg_logprobs": -0.12,
    }
    result = _result_with_provider_details(expected)
    assert extract_google_logprobs(result) == expected
