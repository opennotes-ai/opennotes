from __future__ import annotations

import html

from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.x.api import XTweet


def synthesize_x_scrape(root: XTweet, canonical_url: str) -> ScrapeResult:
    body_html = html.escape(root.text, quote=True).replace("\n", "<br>")
    handle = html.escape(root.author_handle, quote=True)
    name = html.escape(root.author_name, quote=True)
    created_at = html.escape(root.created_at.isoformat(), quote=True)
    html_doc = (
        f'<article class="opennotes-x-root" data-utterance-id="{html.escape(root.id, quote=True)}">'
        '<header class="opennotes-x-root__header">'
        f'<span class="opennotes-x-root__author">@{handle}</span>'
        f'<span class="opennotes-x-root__name">{name}</span>'
        f'<time datetime="{created_at}">{created_at}</time>'
        "</header>"
        f'<div class="opennotes-x-root__body">{body_html}</div>'
        "</article>"
    )
    metadata = ScrapeMetadata.model_validate(
        {
            "title": f"@{root.author_handle} on X",
            "description": root.text[:280],
            "platform": "x",
            "canonical_url": canonical_url,
            "og:title": f"@{root.author_handle} on X",
            "og:description": root.text[:280],
            "source_url": canonical_url,
        }
    )
    return ScrapeResult(
        markdown=(
            f"# @{root.author_handle} ({root.author_name})\n\n"
            f"{root.text}\n\n"
            f"_{root.created_at.isoformat()}_"
        ),
        html=html_doc,
        raw_html=html_doc,
        screenshot=None,
        metadata=metadata,
    )
