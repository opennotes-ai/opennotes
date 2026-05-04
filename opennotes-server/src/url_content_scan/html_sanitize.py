from __future__ import annotations

import re

_COMMENT_RE = re.compile(r"<!--.*?-->", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r"<link\b[^>]*?/?>", re.IGNORECASE | re.DOTALL)


def strip_noise(html: str | None) -> str | None:
    if html is None:
        return None
    if not html:
        return ""

    return _LINK_RE.sub("", _STYLE_RE.sub("", _SCRIPT_RE.sub("", _COMMENT_RE.sub("", html))))
