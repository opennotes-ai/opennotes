"""Public API for Coral comment integration."""

from __future__ import annotations

from .detector import CoralSignal, detect_coral
from .graphql import (
    CoralCommentNode,
    CoralComments,
    CoralFetchError,
    CoralUnsupportedError,
    fetch_coral_comments,
)
from .merge import merge_coral_into_scrape
from .render import render_to_markdown

__all__ = [
    "CoralCommentNode",
    "CoralComments",
    "CoralFetchError",
    "CoralSignal",
    "CoralUnsupportedError",
    "detect_coral",
    "fetch_coral_comments",
    "merge_coral_into_scrape",
    "render_to_markdown",
]
