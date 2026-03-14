from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from src.dbos_workflows.enqueue_utils import (
    DBOSEnqueueTransientError,
    safe_enqueue,
    safe_enqueue_sync,
)


@pytest.mark.asyncio
async def test_safe_enqueue_succeeds_on_first_try():
    result = await safe_enqueue(lambda: "wf-123")
    assert result == "wf-123"


@pytest.mark.asyncio
async def test_safe_enqueue_retries_on_operational_error_then_succeeds():
    call_count = 0

    def flaky_enqueue():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            orig = MagicMock()
            del orig.sqlstate
            raise OperationalError("", {}, orig)
        return "wf-456"

    result = await safe_enqueue(flaky_enqueue)
    assert result == "wf-456"
    assert call_count == 2


@pytest.mark.asyncio
async def test_safe_enqueue_retries_on_attribute_error_sqlstate():
    call_count = 0

    def flaky_enqueue():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AttributeError("'OperationalError' object has no attribute 'sqlstate'")
        return "wf-789"

    result = await safe_enqueue(flaky_enqueue)
    assert result == "wf-789"


@pytest.mark.asyncio
async def test_safe_enqueue_raises_after_retries_exhausted():
    def always_fails():
        raise AttributeError("'OperationalError' object has no attribute 'sqlstate'")

    with pytest.raises(DBOSEnqueueTransientError):
        await safe_enqueue(always_fails)


@pytest.mark.asyncio
async def test_safe_enqueue_does_not_retry_non_transient_errors():
    def bad_enqueue():
        raise ValueError("unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        await safe_enqueue(bad_enqueue)


def test_safe_enqueue_sync_succeeds_on_first_try():
    result = safe_enqueue_sync(lambda: "wf-sync-ok")
    assert result == "wf-sync-ok"


def test_safe_enqueue_sync_retries_on_operational_error():
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            orig = MagicMock()
            del orig.sqlstate
            raise OperationalError("", {}, orig)
        return "wf-sync-retry"

    result = safe_enqueue_sync(flaky)
    assert result == "wf-sync-retry"
    assert call_count == 2


def test_safe_enqueue_sync_raises_after_retries_exhausted():
    def always_fails():
        raise AttributeError("'OperationalError' object has no attribute 'sqlstate'")

    with pytest.raises(DBOSEnqueueTransientError):
        safe_enqueue_sync(always_fails)
