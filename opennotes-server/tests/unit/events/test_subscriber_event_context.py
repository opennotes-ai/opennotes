from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from opentelemetry import baggage, context

from src.events.subscriber import _extract_event_payload_context


@pytest.mark.unit
class TestExtractEventPayloadContext:
    def test_extracts_community_server_id_as_string(self) -> None:
        cs_uuid = uuid4()
        event = MagicMock()
        event.community_server_id = cs_uuid
        event.channel_id = None
        span = MagicMock()

        ctx = _extract_event_payload_context(event, span)

        span.set_attribute.assert_any_call("community_server_id", str(cs_uuid))

        token = context.attach(ctx)
        try:
            assert baggage.get_baggage("community_server_id") == str(cs_uuid)
        finally:
            context.detach(token)

    def test_extracts_string_community_server_id(self) -> None:
        event = MagicMock()
        event.community_server_id = "guild-123"
        event.channel_id = None
        span = MagicMock()

        ctx = _extract_event_payload_context(event, span)

        span.set_attribute.assert_any_call("community_server_id", "guild-123")

        token = context.attach(ctx)
        try:
            assert baggage.get_baggage("community_server_id") == "guild-123"
        finally:
            context.detach(token)

    def test_extracts_channel_id(self) -> None:
        event = MagicMock()
        event.community_server_id = None
        event.channel_id = "ch-456"
        span = MagicMock()

        ctx = _extract_event_payload_context(event, span)

        span.set_attribute.assert_any_call("discord.channel_id", "ch-456")

        token = context.attach(ctx)
        try:
            assert baggage.get_baggage("discord.channel_id") == "ch-456"
        finally:
            context.detach(token)

    def test_extracts_both_community_server_id_and_channel_id(self) -> None:
        event = MagicMock()
        event.community_server_id = "guild-789"
        event.channel_id = "ch-012"
        span = MagicMock()

        ctx = _extract_event_payload_context(event, span)

        span.set_attribute.assert_any_call("community_server_id", "guild-789")
        span.set_attribute.assert_any_call("discord.channel_id", "ch-012")

        token = context.attach(ctx)
        try:
            assert baggage.get_baggage("community_server_id") == "guild-789"
            assert baggage.get_baggage("discord.channel_id") == "ch-012"
        finally:
            context.detach(token)

    def test_no_attributes_when_fields_missing(self) -> None:
        event = MagicMock(spec=[])
        span = MagicMock()

        ctx = _extract_event_payload_context(event, span)

        span.set_attribute.assert_not_called()

        token = context.attach(ctx)
        try:
            assert baggage.get_baggage("community_server_id") is None
            assert baggage.get_baggage("discord.channel_id") is None
        finally:
            context.detach(token)

    def test_no_attributes_when_fields_are_none(self) -> None:
        event = MagicMock()
        event.community_server_id = None
        event.channel_id = None
        span = MagicMock()

        _extract_event_payload_context(event, span)

        span.set_attribute.assert_not_called()
