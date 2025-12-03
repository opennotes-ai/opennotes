from typing import Any

from src.webhooks.types import (
    Embed,
    InteractionCallbackData,
    InteractionResponse,
    InteractionResponseType,
)


def create_message_response(
    content: str | None = None,
    embeds: list[Embed] | list[dict[str, Any]] | None = None,
    components: list[dict[str, Any]] | None = None,
    ephemeral: bool = False,
    is_update: bool = False,
) -> dict[str, Any]:
    flags = 64 if ephemeral else None

    # Convert dict embeds to Embed objects if needed
    typed_embeds: list[Embed] | None = None
    if embeds:
        typed_embeds = (
            [Embed(**e) for e in embeds]  # type: ignore[arg-type]
            if isinstance(embeds[0], dict)
            else embeds  # type: ignore[assignment]
        )

    data = InteractionCallbackData(
        content=content,
        embeds=typed_embeds,
        components=components,
        flags=flags,
    )

    response_type = (
        InteractionResponseType.UPDATE_MESSAGE
        if is_update
        else InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE
    )

    return InteractionResponse(type=response_type, data=data).model_dump(exclude_none=True)
