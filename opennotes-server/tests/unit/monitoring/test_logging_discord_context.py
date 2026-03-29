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
class TestPlatformContextInLogs:
    def test_platform_type_from_baggage_added_to_log(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("platform.type", "discord", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("platform.type") == "discord"
        finally:
            context.detach(token)

    def test_platform_community_id_from_baggage_added_to_log(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("platform.community_id", "444555666", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("platform.community_id") == "444555666"
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

    def test_all_platform_context_fields_from_baggage(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        ctx = context.get_current()
        ctx = baggage.set_baggage("platform.type", "discord", ctx)
        ctx = baggage.set_baggage("platform.community_id", "222", ctx)
        ctx = baggage.set_baggage("community_server_id", "333", ctx)
        token = context.attach(ctx)

        try:
            log_data: dict[str, Any] = {}
            formatter.add_fields(log_data, log_record, {})
            assert log_data.get("platform.type") == "discord"
            assert log_data.get("platform.community_id") == "222"
            assert log_data.get("community_server_id") == "333"
        finally:
            context.detach(token)

    def test_missing_baggage_does_not_add_fields(
        self, formatter: CustomJsonFormatter, log_record: logging.LogRecord
    ) -> None:
        log_data: dict[str, Any] = {}
        formatter.add_fields(log_data, log_record, {})

        assert "platform.type" not in log_data
        assert "platform.community_id" not in log_data
        assert "community_server_id" not in log_data
