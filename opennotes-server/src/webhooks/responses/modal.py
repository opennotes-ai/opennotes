from typing import Any

from src.webhooks.types import InteractionResponseType


def create_modal_response(
    custom_id: str,
    title: str,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": InteractionResponseType.MODAL,
        "data": {
            "custom_id": custom_id,
            "title": title,
            "components": components,
        },
    }
