from __future__ import annotations

import asyncio
import sys
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MODULE_PATH = "src.cache.redis_client"


@pytest.fixture(autouse=True)
def _reset_shared_redis():
    mod = sys.modules.get(MODULE_PATH)
    if mod is None:
        import importlib

        mod = importlib.import_module(MODULE_PATH)

    mod._thread_local.redis = None
    mod._thread_local.loop = None
    yield
    mod._thread_local.redis = None
    mod._thread_local.loop = None


def _get_module():
    return sys.modules[MODULE_PATH]


def _make_mock_redis(*, ping_ok: bool = True) -> AsyncMock:
    client = AsyncMock()
    if ping_ok:
        client.ping.return_value = True
    else:
        client.ping.side_effect = ConnectionError("gone")
    client.close.return_value = None
    return client


@pytest.mark.asyncio
async def test_creates_new_connection_on_first_call():
    mock_client = _make_mock_redis()

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=mock_client) as mock_create:
        from src.cache.redis_client import get_shared_redis_client

        result = await get_shared_redis_client("redis://localhost")

    mod = _get_module()
    assert result is mock_client
    mock_create.assert_awaited_once()
    assert mod._thread_local.redis is mock_client
    assert mod._thread_local.loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_reuses_existing_connection_on_same_loop():
    mock_client = _make_mock_redis()

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=mock_client) as mock_create:
        from src.cache.redis_client import get_shared_redis_client

        first = await get_shared_redis_client("redis://localhost")
        second = await get_shared_redis_client("redis://localhost")

    assert first is second
    mock_create.assert_awaited_once()
    mock_client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconnects_when_ping_fails():
    mod = _get_module()
    stale_client = _make_mock_redis(ping_ok=False)
    fresh_client = _make_mock_redis()

    mod._thread_local.redis = stale_client
    mod._thread_local.loop = asyncio.get_running_loop()

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=fresh_client) as mock_create:
        from src.cache.redis_client import get_shared_redis_client

        result = await get_shared_redis_client("redis://localhost")

    assert result is fresh_client
    mock_create.assert_awaited_once()
    stale_client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_detects_event_loop_change_and_creates_new_connection():
    mod = _get_module()
    old_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    old_client = _make_mock_redis()
    new_client = _make_mock_redis()

    mod._thread_local.redis = old_client
    mod._thread_local.loop = old_loop

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=new_client) as mock_create:
        from src.cache.redis_client import get_shared_redis_client

        result = await get_shared_redis_client("redis://localhost")

    assert result is new_client
    mock_create.assert_awaited_once()
    old_client.close.assert_awaited_once()
    assert mod._thread_local.redis is new_client
    assert mod._thread_local.loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_loop_change_tolerates_close_failure():
    mod = _get_module()
    old_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    old_client = _make_mock_redis()
    old_client.close.side_effect = RuntimeError("close failed")
    new_client = _make_mock_redis()

    mod._thread_local.redis = old_client
    mod._thread_local.loop = old_loop

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=new_client):
        from src.cache.redis_client import get_shared_redis_client

        result = await get_shared_redis_client("redis://localhost")

    assert result is new_client
    old_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_tracks_loop_after_creation():
    mod = _get_module()
    mock_client = _make_mock_redis()

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=mock_client):
        from src.cache.redis_client import get_shared_redis_client

        await get_shared_redis_client("redis://localhost")

    assert mod._thread_local.loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_thread_local_isolation():
    mod = _get_module()
    main_client = _make_mock_redis()
    thread_client = _make_mock_redis()

    with patch(f"{MODULE_PATH}.create_redis_connection", return_value=main_client):
        from src.cache.redis_client import get_shared_redis_client

        main_result = await get_shared_redis_client("redis://localhost")

    assert main_result is main_client
    assert mod._thread_local.redis is main_client

    thread_saw_main: list[bool] = []
    thread_created_own: list[bool] = []

    def _worker():
        pre_existing = getattr(mod._thread_local, "redis", None)
        thread_saw_main.append(pre_existing is main_client)
        loop = asyncio.new_event_loop()
        try:
            with patch(f"{MODULE_PATH}.create_redis_connection", return_value=thread_client):
                result = loop.run_until_complete(get_shared_redis_client("redis://localhost"))
                thread_created_own.append(result is thread_client)
        finally:
            loop.close()

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    assert thread_saw_main == [False]
    assert thread_created_own == [True]
    assert mod._thread_local.redis is main_client
