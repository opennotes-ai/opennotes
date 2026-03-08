import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.connection_retry import (
    async_connect_with_retry,
    is_transient_connection_error,
    sync_connect_with_retry,
)


class TestIsTransientConnectionError:
    def test_detects_gaierror(self):
        exc = socket.gaierror(-3, "Temporary failure in name resolution")
        assert is_transient_connection_error(exc) is True

    def test_detects_connection_refused(self):
        exc = ConnectionRefusedError("Connection refused")
        assert is_transient_connection_error(exc) is True

    def test_detects_connection_reset_error(self):
        exc = ConnectionResetError(104, "Connection reset by peer")
        assert is_transient_connection_error(exc) is True

    def test_detects_connection_aborted_error(self):
        exc = ConnectionAbortedError("Connection aborted")
        assert is_transient_connection_error(exc) is True

    def test_returns_false_for_value_error(self):
        assert is_transient_connection_error(ValueError("bad")) is False

    def test_returns_false_for_auth_error(self):
        assert is_transient_connection_error(Exception("password authentication failed")) is False

    def test_does_not_retry_permission_error(self):
        assert is_transient_connection_error(PermissionError("Permission denied")) is False

    def test_does_not_retry_file_not_found_error(self):
        assert is_transient_connection_error(FileNotFoundError("No such file")) is False

    def test_does_not_retry_bare_oserror(self):
        assert is_transient_connection_error(OSError("generic OS error")) is False


class TestAsyncConnectWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        creator = AsyncMock(return_value="conn")
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = await connect()
        assert result == "conn"
        assert creator.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_gaierror_then_succeeds(self):
        creator = AsyncMock(
            side_effect=[
                socket.gaierror(-3, "Temporary failure"),
                socket.gaierror(-3, "Temporary failure"),
                "conn",
            ]
        )
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = await connect()
        assert result == "conn"
        assert creator.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_retries_exhausted(self):
        creator = AsyncMock(side_effect=socket.gaierror(-3, "Temporary failure"))
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(socket.gaierror):
            await connect()
        assert creator.call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_does_not_retry_non_transient_errors(self):
        creator = AsyncMock(side_effect=ValueError("bad config"))
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(ValueError, match="bad config"):
            await connect()
        assert creator.call_count == 1

    @pytest.mark.asyncio
    async def test_uses_exponential_backoff(self):
        call_times: list[float] = []

        async def timed_creator():
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise socket.gaierror(-3, "fail")
            return "conn"

        connect = async_connect_with_retry(timed_creator, max_retries=3, backoff_base=0.05)
        await connect()
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay1 >= 0.03  # ~0.05 with jitter
        assert delay2 >= 0.06  # ~0.10 with jitter
        assert delay2 > delay1

    @pytest.mark.asyncio
    async def test_emits_metric_on_success_after_retry(self):
        creator = AsyncMock(side_effect=[socket.gaierror(-3, "fail"), "conn"])
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_get.return_value = mock_counter
            connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
            await connect()
            mock_counter.add.assert_called_once_with(1, {"outcome": "success"})

    @pytest.mark.asyncio
    async def test_emits_metric_on_exhausted(self):
        creator = AsyncMock(side_effect=socket.gaierror(-3, "fail"))
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_get.return_value = mock_counter
            connect = async_connect_with_retry(creator, max_retries=2, backoff_base=0.01)
            with pytest.raises(socket.gaierror):
                await connect()
            mock_counter.add.assert_called_once_with(1, {"outcome": "exhausted"})

    @pytest.mark.asyncio
    async def test_no_metric_on_first_attempt_success(self):
        creator = AsyncMock(return_value="conn")
        with patch("src.common.connection_retry._get_metric") as mock_get:
            connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
            await connect()
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_retries_on_connection_refused(self):
        creator = AsyncMock(side_effect=[ConnectionRefusedError("refused"), "conn"])
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = await connect()
        assert result == "conn"
        assert creator.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_connection_reset_error(self):
        creator = AsyncMock(
            side_effect=[ConnectionResetError(104, "Connection reset by peer"), "conn"]
        )
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = await connect()
        assert result == "conn"
        assert creator.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_permission_error(self):
        creator = AsyncMock(side_effect=PermissionError("Permission denied"))
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(PermissionError, match="Permission denied"):
            await connect()
        assert creator.call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_file_not_found_error(self):
        creator = AsyncMock(side_effect=FileNotFoundError("No such file"))
        connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(FileNotFoundError, match="No such file"):
            await connect()
        assert creator.call_count == 1

    @pytest.mark.asyncio
    async def test_metric_failure_does_not_mask_success(self):
        creator = AsyncMock(side_effect=[socket.gaierror(-3, "fail"), "conn"])
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_counter.add.side_effect = RuntimeError("metrics broken")
            mock_get.return_value = mock_counter
            connect = async_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
            result = await connect()
            assert result == "conn"

    @pytest.mark.asyncio
    async def test_metric_failure_does_not_mask_exhausted_error(self):
        creator = AsyncMock(side_effect=socket.gaierror(-3, "fail"))
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_counter.add.side_effect = RuntimeError("metrics broken")
            mock_get.return_value = mock_counter
            connect = async_connect_with_retry(creator, max_retries=2, backoff_base=0.01)
            with pytest.raises(socket.gaierror):
                await connect()

    @pytest.mark.asyncio
    async def test_zero_retries_raises_immediately(self):
        creator = AsyncMock(side_effect=socket.gaierror(-3, "fail"))
        connect = async_connect_with_retry(creator, max_retries=0, backoff_base=0.01)
        with pytest.raises(socket.gaierror):
            await connect()
        assert creator.call_count == 1


class TestSyncConnectWithRetry:
    def test_succeeds_on_first_attempt(self):
        creator = MagicMock(return_value="conn")
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = connect()
        assert result == "conn"
        assert creator.call_count == 1

    def test_retries_on_connection_refused_then_succeeds(self):
        creator = MagicMock(side_effect=[ConnectionRefusedError("refused"), "conn"])
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        result = connect()
        assert result == "conn"
        assert creator.call_count == 2

    def test_raises_after_retries_exhausted(self):
        creator = MagicMock(side_effect=ConnectionRefusedError("refused"))
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(ConnectionRefusedError):
            connect()
        assert creator.call_count == 4  # 1 initial + 3 retries

    def test_does_not_retry_non_transient_errors(self):
        creator = MagicMock(side_effect=ValueError("bad"))
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(ValueError, match="bad"):
            connect()
        assert creator.call_count == 1

    def test_emits_metric_on_success_after_retry(self):
        creator = MagicMock(side_effect=[socket.gaierror(-3, "fail"), "conn"])
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_get.return_value = mock_counter
            connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
            connect()
            mock_counter.add.assert_called_once_with(1, {"outcome": "success"})

    def test_emits_metric_on_exhausted(self):
        creator = MagicMock(side_effect=socket.gaierror(-3, "fail"))
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_get.return_value = mock_counter
            connect = sync_connect_with_retry(creator, max_retries=2, backoff_base=0.01)
            with pytest.raises(socket.gaierror):
                connect()
            mock_counter.add.assert_called_once_with(1, {"outcome": "exhausted"})

    def test_does_not_retry_permission_error(self):
        creator = MagicMock(side_effect=PermissionError("Permission denied"))
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(PermissionError, match="Permission denied"):
            connect()
        assert creator.call_count == 1

    def test_does_not_retry_file_not_found_error(self):
        creator = MagicMock(side_effect=FileNotFoundError("No such file"))
        connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
        with pytest.raises(FileNotFoundError, match="No such file"):
            connect()
        assert creator.call_count == 1

    def test_metric_failure_does_not_mask_success(self):
        creator = MagicMock(side_effect=[socket.gaierror(-3, "fail"), "conn"])
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_counter.add.side_effect = RuntimeError("metrics broken")
            mock_get.return_value = mock_counter
            connect = sync_connect_with_retry(creator, max_retries=3, backoff_base=0.01)
            result = connect()
            assert result == "conn"

    def test_metric_failure_does_not_mask_exhausted_error(self):
        creator = MagicMock(side_effect=socket.gaierror(-3, "fail"))
        with patch("src.common.connection_retry._get_metric") as mock_get:
            mock_counter = MagicMock()
            mock_counter.add.side_effect = RuntimeError("metrics broken")
            mock_get.return_value = mock_counter
            connect = sync_connect_with_retry(creator, max_retries=2, backoff_base=0.01)
            with pytest.raises(socket.gaierror):
                connect()
