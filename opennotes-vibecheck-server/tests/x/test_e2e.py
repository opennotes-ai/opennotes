from __future__ import annotations

import json
from pathlib import Path

import httpx

from src.x.api import fetch_x_conversation
from src.x.merge import merge_x_into_scrape
from src.x.synthesize import synthesize_x_scrape

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "conversation_100.json"


async def test_fixture_pipeline_produces_threaded_utterance_html() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/2/tweets/100":
            return httpx.Response(200, json=fixture["root"])
        return httpx.Response(200, json=fixture["search_pages"][0])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        conversation = await fetch_x_conversation("100", bearer="token", http=http)

    scrape = synthesize_x_scrape(conversation.root, "https://x.com/i/status/100")
    merged = merge_x_into_scrape(scrape, conversation)

    assert merged.html is not None
    assert "Root post from fixture" in merged.html
    assert merged.html.count("data-utterance-id=") == 3
    assert '<ol class="opennotes-comment__replies">' in merged.html
