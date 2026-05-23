"""Tests for bounded-backoff saturation retries in TokenGate.

Ported behaviour from vibecheck PR586 (fa777053): gate retries with
exponential backoff + jitter on saturated acquire (returns False), instead
of busy-looping at a fixed poll interval.
"""

from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from src.dbos_workflows.token_bucket.gate import (
    DEFAULT_SATURATION_RETRY_BASE_MS,
    DEFAULT_SATURATION_RETRY_JITTER_MS,
    DEFAULT_SATURATION_RETRY_MAX_MS,
    TokenGate,
    _saturation_sleep_ms,
)


class TestSaturationSleepMs:
    def test_first_retry_returns_base(self) -> None:
        result = _saturation_sleep_ms(
            retry_index=1,
            base_ms=500,
            max_ms=4000,
            jitter_ms=0,
            rng=random.Random(0),
        )
        assert result == pytest.approx(500.0)

    def test_second_retry_doubles(self) -> None:
        result = _saturation_sleep_ms(
            retry_index=2,
            base_ms=500,
            max_ms=4000,
            jitter_ms=0,
            rng=random.Random(0),
        )
        assert result == pytest.approx(1000.0)

    def test_capped_at_max(self) -> None:
        result = _saturation_sleep_ms(
            retry_index=10,
            base_ms=500,
            max_ms=4000,
            jitter_ms=0,
            rng=random.Random(0),
        )
        assert result == pytest.approx(4000.0)

    def test_jitter_adds_to_sleep(self) -> None:
        rng = random.Random(42)
        result = _saturation_sleep_ms(
            retry_index=1,
            base_ms=500,
            max_ms=4000,
            jitter_ms=250,
            rng=rng,
        )
        assert result >= 500.0
        assert result <= 750.0


class TestTokenGateSaturationRetry:
    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_retries_on_saturation_with_backoff(self, mock_acquire, mock_dbos) -> None:
        mock_dbos.workflow_id = "wf-sat"
        sleep_calls: list[float] = []
        mock_dbos.sleep.side_effect = lambda d: sleep_calls.append(d)
        mock_acquire.side_effect = [False, False, True]

        gate = TokenGate(
            pool="default",
            weight=1,
            saturation_retry_base_ms=500,
            saturation_retry_max_ms=4000,
            saturation_retry_jitter_ms=0,
            max_wait_seconds=60.0,
        )
        gate.acquire()

        assert mock_acquire.call_count == 3
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == pytest.approx(0.5)
        assert sleep_calls[1] == pytest.approx(1.0)

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_sleep_is_exponential_up_to_max(self, mock_acquire, mock_dbos) -> None:
        mock_dbos.workflow_id = "wf-exp"
        sleep_calls: list[float] = []
        mock_dbos.sleep.side_effect = lambda d: sleep_calls.append(d)
        mock_acquire.side_effect = [False, False, False, False, False, True]

        gate = TokenGate(
            pool="default",
            weight=1,
            saturation_retry_base_ms=500,
            saturation_retry_max_ms=2000,
            saturation_retry_jitter_ms=0,
            max_wait_seconds=3600.0,
        )
        gate.acquire()

        assert sleep_calls == pytest.approx([0.5, 1.0, 2.0, 2.0, 2.0])

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_timeout_still_respected(self, mock_acquire, mock_dbos) -> None:
        mock_dbos.workflow_id = "wf-timeout"
        mock_acquire.return_value = False

        gate = TokenGate(
            pool="default",
            weight=1,
            saturation_retry_base_ms=2000,
            saturation_retry_max_ms=4000,
            saturation_retry_jitter_ms=0,
            max_wait_seconds=3.0,
        )
        with pytest.raises(TimeoutError, match="timed out"):
            gate.acquire()

    @patch("src.dbos_workflows.token_bucket.gate.DBOS")
    @patch("src.dbos_workflows.token_bucket.gate.try_acquire_tokens")
    def test_defaults_are_bounded(self, mock_acquire, mock_dbos) -> None:
        assert DEFAULT_SATURATION_RETRY_BASE_MS > 0
        assert DEFAULT_SATURATION_RETRY_MAX_MS >= DEFAULT_SATURATION_RETRY_BASE_MS
        assert DEFAULT_SATURATION_RETRY_JITTER_MS >= 0


class TestTokenGateSaturationRetryDefaults:
    def test_gate_has_saturation_retry_defaults(self) -> None:
        gate = TokenGate()
        assert gate.saturation_retry_base_ms == DEFAULT_SATURATION_RETRY_BASE_MS
        assert gate.saturation_retry_max_ms == DEFAULT_SATURATION_RETRY_MAX_MS
        assert gate.saturation_retry_jitter_ms == DEFAULT_SATURATION_RETRY_JITTER_MS

    def test_gate_accepts_custom_saturation_retry_params(self) -> None:
        gate = TokenGate(
            saturation_retry_base_ms=100,
            saturation_retry_max_ms=1000,
            saturation_retry_jitter_ms=50,
        )
        assert gate.saturation_retry_base_ms == 100
        assert gate.saturation_retry_max_ms == 1000
        assert gate.saturation_retry_jitter_ms == 50
