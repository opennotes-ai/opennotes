from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from src.jobs.orchestrator import EXTRACT_TRANSIENT_MAX_ATTEMPTS
from src.services.gemini_agent import MAX_VERTEX_429_ATTEMPTS, run_vertex_agent_with_retry


def _exc(status_code: int) -> ModelHTTPError:
    return ModelHTTPError(status_code=status_code, model_name="gemini-2.5-flash", body=None)


def _mock_agent(*side_effects: object) -> MagicMock:
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=list(side_effects))
    return agent


async def test_retries_on_429_then_succeeds() -> None:
    fake_result = object()
    agent = _mock_agent(_exc(429), fake_result)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await run_vertex_agent_with_retry(agent)

    assert result is fake_result
    assert agent.run.call_count == 2
    assert mock_sleep.call_count == 1


async def test_exhausts_all_attempts_and_reraises_429() -> None:
    agent = _mock_agent(_exc(429), _exc(429), _exc(429))

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, pytest.raises(ModelHTTPError) as exc_info:
        await run_vertex_agent_with_retry(agent)

    assert exc_info.value.status_code == 429
    assert agent.run.call_count == MAX_VERTEX_429_ATTEMPTS
    assert mock_sleep.call_count == MAX_VERTEX_429_ATTEMPTS - 1


async def test_non_429_not_retried() -> None:
    agent = _mock_agent(_exc(400))

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, pytest.raises(ModelHTTPError) as exc_info:
        await run_vertex_agent_with_retry(agent)

    assert exc_info.value.status_code == 400
    assert agent.run.call_count == 1
    mock_sleep.assert_not_called()


def test_extract_transient_max_attempts_is_3() -> None:
    assert EXTRACT_TRANSIENT_MAX_ATTEMPTS == 3
