from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.middleware.discord_context import DiscordContextMiddleware


@pytest.mark.unit
class TestDiscordContextMiddleware:
    def test_channel_id_header_sets_span_attribute_and_baggage(self) -> None:
        app = FastAPI()
        app.add_middleware(DiscordContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with (
            patch(
                "src.middleware.discord_context.trace.get_current_span",
                return_value=mock_span,
            ),
            patch("src.middleware.discord_context.baggage.set_baggage") as mock_baggage,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={"x-channel-id": "987654321"},
            )

        assert response.status_code == 200
        assert captured_attributes.get("discord.channel_id") == "987654321"

        baggage_calls = [call[0] for call in mock_baggage.call_args_list]
        assert any(
            call[0] == "discord.channel_id" and call[1] == "987654321" for call in baggage_calls
        )

    def test_guild_id_and_channel_id_both_propagated(self) -> None:
        app = FastAPI()
        app.add_middleware(DiscordContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with (
            patch(
                "src.middleware.discord_context.trace.get_current_span",
                return_value=mock_span,
            ),
            patch("src.middleware.discord_context.baggage.set_baggage") as mock_baggage,
        ):
            client = TestClient(app)
            response = client.get(
                "/test",
                headers={
                    "x-guild-id": "111222333",
                    "x-channel-id": "444555666",
                },
            )

        assert response.status_code == 200
        assert captured_attributes.get("discord.guild_id") == "111222333"
        assert captured_attributes.get("discord.channel_id") == "444555666"

        baggage_calls = [call[0] for call in mock_baggage.call_args_list]
        assert any(
            call[0] == "discord.guild_id" and call[1] == "111222333" for call in baggage_calls
        )
        assert any(
            call[0] == "discord.channel_id" and call[1] == "444555666" for call in baggage_calls
        )

    def test_missing_channel_id_does_not_set_attribute(self) -> None:
        app = FastAPI()
        app.add_middleware(DiscordContextMiddleware)

        captured_attributes: dict[str, str] = {}

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        mock_span = MagicMock()
        mock_span.set_attribute = lambda k, v: captured_attributes.__setitem__(k, v)

        with patch(
            "src.middleware.discord_context.trace.get_current_span",
            return_value=mock_span,
        ):
            client = TestClient(app)
            response = client.get("/test")

        assert response.status_code == 200
        assert "discord.channel_id" not in captured_attributes
