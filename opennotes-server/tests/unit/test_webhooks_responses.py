from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.webhooks.responses.followup import send_followup_message
from src.webhooks.responses.message import create_message_response
from src.webhooks.responses.modal import create_modal_response
from src.webhooks.types import InteractionResponseType

pytestmark = pytest.mark.unit


class TestMessageResponse:
    def test_create_message_response_simple(self):
        response = create_message_response(content="Hello, world!")

        assert response["type"] == InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE
        assert response["data"]["content"] == "Hello, world!"
        assert "flags" not in response["data"]

    def test_create_message_response_ephemeral(self):
        response = create_message_response(content="Secret message", ephemeral=True)

        assert response["data"]["flags"] == 64

    def test_create_message_response_with_embeds(self):
        embeds = [{"title": "Test Embed", "description": "This is a test", "color": 0x5865F2}]

        response = create_message_response(content="With embed", embeds=embeds)

        assert response["data"]["content"] == "With embed"
        assert response["data"]["embeds"] == embeds
        assert len(response["data"]["embeds"]) == 1

    def test_create_message_response_with_components(self):
        components = [
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": "Click me", "custom_id": "button_1"}
                ],
            }
        ]

        response = create_message_response(content="With button", components=components)

        assert response["data"]["content"] == "With button"
        assert response["data"]["components"] == components

    def test_create_message_response_update(self):
        response = create_message_response(content="Updated", is_update=True)

        assert response["type"] == InteractionResponseType.UPDATE_MESSAGE

    def test_create_message_response_update_with_ephemeral(self):
        response = create_message_response(content="Updated secret", is_update=True, ephemeral=True)

        assert response["type"] == InteractionResponseType.UPDATE_MESSAGE
        assert response["data"]["flags"] == 64

    def test_create_message_response_all_parameters(self):
        embeds = [{"title": "Title"}]
        components = [{"type": 1}]

        response = create_message_response(
            content="Full message",
            embeds=embeds,
            components=components,
            ephemeral=True,
            is_update=False,
        )

        assert response["data"]["content"] == "Full message"
        assert response["data"]["embeds"] == embeds
        assert response["data"]["components"] == components
        assert response["data"]["flags"] == 64

    def test_create_message_response_no_content(self):
        embeds = [{"title": "Just embed"}]
        response = create_message_response(embeds=embeds)

        assert response["data"].get("content") is None
        assert response["data"]["embeds"] == embeds

    def test_create_message_response_exclude_none(self):
        response = create_message_response(content="Test")

        assert "embeds" not in response["data"]
        assert "components" not in response["data"]


class TestFollowupMessage:
    @pytest.mark.asyncio
    async def test_send_followup_message_success(self):
        app_id = "123456789"
        token = "interaction_token"
        content = "Followup message"

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "message_123", "content": content}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await send_followup_message(app_id, token, content=content)

        assert result == {"id": "message_123", "content": content}
        mock_client.post.assert_called_once()

        call_args = mock_client.post.call_args
        assert f"webhooks/{app_id}/{token}" in call_args[0][0]
        assert call_args[1]["json"]["content"] == content

    @pytest.mark.asyncio
    async def test_send_followup_message_with_embeds(self):
        app_id = "123456789"
        token = "token"
        embeds = [{"title": "Embed"}]

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_followup_message(app_id, token, embeds=embeds)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["embeds"] == embeds

    @pytest.mark.asyncio
    async def test_send_followup_message_with_components(self):
        app_id = "123456789"
        token = "token"
        components = [{"type": 1}]

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_followup_message(app_id, token, components=components)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["components"] == components

    @pytest.mark.asyncio
    async def test_send_followup_message_ephemeral(self):
        app_id = "123456789"
        token = "token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_followup_message(app_id, token, content="Secret", ephemeral=True)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["flags"] == 64

    @pytest.mark.asyncio
    async def test_send_followup_message_http_error(self):
        app_id = "123456789"
        token = "token"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await send_followup_message(app_id, token, content="Test")

        assert result is None

    @pytest.mark.asyncio
    async def test_send_followup_message_auth_header(self):
        app_id = "123456789"
        token = "token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch("src.webhooks.responses.followup.settings") as mock_settings,
        ):
            mock_settings.DISCORD_BOT_TOKEN = "test_bot_token"

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_followup_message(app_id, token, content="Test")

        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bot test_bot_token"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_followup_message_timeout(self):
        app_id = "123456789"
        token = "token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "msg"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_followup_message(app_id, token, content="Test")

        call_args = mock_client.post.call_args
        assert call_args[1]["timeout"] == 10.0


class TestModalResponse:
    def test_create_modal_response_simple(self):
        custom_id = "modal_1"
        title = "Test Modal"
        components = [
            {
                "type": 1,
                "components": [{"type": 4, "custom_id": "input_1", "label": "Name", "style": 1}],
            }
        ]

        response = create_modal_response(custom_id, title, components)

        assert response["type"] == InteractionResponseType.MODAL
        assert "data" in response
        data = response["data"]
        if isinstance(data, dict):
            assert "custom_id" in data or "components" in data

    def test_create_modal_response_multiple_inputs(self):
        custom_id = "modal_2"
        title = "Survey"
        components = [
            {
                "type": 1,
                "components": [{"type": 4, "custom_id": "name", "label": "Name", "style": 1}],
            },
            {
                "type": 1,
                "components": [
                    {"type": 4, "custom_id": "feedback", "label": "Feedback", "style": 2}
                ],
            },
        ]

        response = create_modal_response(custom_id, title, components)

        assert response["type"] == InteractionResponseType.MODAL
        assert "data" in response

    def test_create_modal_response_exclude_none(self):
        custom_id = "modal_3"
        title = "Simple"
        components = [{"type": 1}]

        response = create_modal_response(custom_id, title, components)

        assert "type" in response
        assert "data" in response

    def test_create_modal_response_unicode_title(self):
        custom_id = "modal_unicode"
        title = "测试模态框 🎉"
        components = [{"type": 1}]

        response = create_modal_response(custom_id, title, components)

        assert response["type"] == InteractionResponseType.MODAL
        assert "data" in response
