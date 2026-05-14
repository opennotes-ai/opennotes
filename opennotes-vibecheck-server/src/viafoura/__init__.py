"""Public API for Viafoura comment integration."""

from __future__ import annotations

from .api import (
    ViafouraCommentNode,
    ViafouraComments,
    ViafouraFetchError,
    ViafouraUnsupportedError,
    fetch_viafoura_comments,
)
from .detector import ViafouraSignal, detect_viafoura
from .merge import merge_viafoura_into_scrape
from .render import render_comments_to_html, render_to_markdown
from .tier2_actions import build_viafoura_actions

__all__ = [
    "ViafouraCommentNode",
    "ViafouraComments",
    "ViafouraFetchError",
    "ViafouraSignal",
    "ViafouraUnsupportedError",
    "build_viafoura_actions",
    "detect_viafoura",
    "fetch_viafoura_comments",
    "merge_viafoura_into_scrape",
    "render_comments_to_html",
    "render_to_markdown",
]
