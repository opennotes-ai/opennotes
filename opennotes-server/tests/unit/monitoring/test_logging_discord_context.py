import logging
from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry import baggage, context

from src.monitoring.logging import CustomJsonFormatter


@pytest.fixture
def formatter() -> CustomJsonFormatter:
    with patch("src.config.get_settings", side_effect=ImportError("no settings")):
        return CustomJsonFormatter("%(message)s", timestamp=True)


@pytest.fixture
def log_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )


@pytest.mark.unit
class TestDiscordContextInLogs:
    def test_guild_id_from_baggage_added_to_log(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("discord.guild_id", "111222333", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("discord.guild_id") == "111222333"
        finally:
            context.detach(token)

    def test_channel_id_from_baggage_added_to_log(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("discord.channel_id", "444555666", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("discord.channel_id") == "444555666"
        finally:
            context.detach(token)

    def test_community_server_id_from_baggage_added_to_log(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("community_server_id", "cs-uuid-123", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("community_server_id") == "cs-uuid-123"
        finally:
            context.detach(token)

    def test_all_discord_context_fields_from_baggage(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("discord.guild_id", "111", ctx)
        ctx = baggage.set_baggage("discord.channel_id", "222", ctx)
        ctx = baggage.set_baggage("community_server_id", "333", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("discord.guild_id") == "111"
            assert log_data.get("discord.channel_id") == "222"
            assert log_data.get("community_server_id") == "333"
        finally:
            context.detach(token)

    def test_missing_baggage_does_not_add_fields(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, log_record, {})

        assert "discord.guild_id" not in log_data
        assert "discord.channel_id" not in log_data
        assert "community_server_id" not in log_data
