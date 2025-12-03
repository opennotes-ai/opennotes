from src.webhooks.types import InteractionResponse, InteractionResponseType


def create_deferred_response(is_update: bool = False) -> dict[str, int]:
    response_type = (
        InteractionResponseType.DEFERRED_UPDATE_MESSAGE
        if is_update
        else InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    )

    return InteractionResponse(type=response_type).model_dump()
