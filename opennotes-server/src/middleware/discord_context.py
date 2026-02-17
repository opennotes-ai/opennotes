"""
Middleware to extract Discord context headers and set them as span attributes.

This middleware extracts X-Discord-* headers from incoming requests and adds them
as attributes to the current OpenTelemetry span for distributed tracing visibility.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from opentelemetry import baggage, context, trace
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class DiscordContextMiddleware(BaseHTTPMiddleware):
    """Extract Discord context headers and set them as span attributes and baggage."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        span = trace.get_current_span()

        discord_user_id = request.headers.get("x-discord-user-id")
        discord_username = request.headers.get("x-discord-username")
        discord_display_name = request.headers.get("x-discord-display-name")
        guild_id = request.headers.get("x-guild-id")
        channel_id = request.headers.get("x-channel-id")
        request_id = request.headers.get("x-request-id")

        ctx = context.get_current()

        if discord_user_id:
            span.set_attribute("discord.user_id", discord_user_id)
            ctx = baggage.set_baggage("discord.user_id", discord_user_id, ctx)

        if discord_username:
            span.set_attribute("discord.username", discord_username)
            ctx = baggage.set_baggage("discord.username", discord_username, ctx)

        if discord_display_name:
            span.set_attribute("discord.display_name", discord_display_name)

        if guild_id:
            span.set_attribute("discord.guild_id", guild_id)
            ctx = baggage.set_baggage("discord.guild_id", guild_id, ctx)

        if channel_id:
            span.set_attribute("discord.channel_id", channel_id)
            ctx = baggage.set_baggage("discord.channel_id", channel_id, ctx)

        if request_id:
            span.set_attribute("http.request_id", request_id)
            ctx = baggage.set_baggage("request_id", request_id, ctx)

        token = context.attach(ctx)
        try:
            response = await call_next(request)
        finally:
            context.detach(token)

        return response
