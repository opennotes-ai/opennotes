"""Post-scrape quality classifier (TASK-1488.03).

Pure-function classifier mapping a `ScrapeResult` / `CachedScrape` into
one of four states the scrape ladder dispatches on:

    AUTH_WALL          terminal — DO NOT escalate (ToS line: bypassing
                       login is off-limits).
    INTERSTITIAL       escalate — CF/JS-required challenge that a richer
                       fetch tier (interact / browser session) might pass.
    LEGITIMATELY_EMPTY terminal — page exists but has no fact-checkable
                       content (404, deleted, empty bundle).
    OK                 proceed — pass the bundle to Gemini extraction.

Heuristic priority order (load-bearing):

    AUTH_WALL > INTERSTITIAL > LEGITIMATELY_EMPTY > OK

A login wall sitting *under* a CF challenge MUST classify AUTH_WALL.
Misclassifying it as INTERSTITIAL would feed the interact-tier ladder
into an attempt-to-bypass-auth, which is a ToS violation. The order is
encoded explicitly via early returns; never reorder without re-running
the priority tests in `tests/unit/test_scrape_quality.py`.

Replaces the inline 'no markdown' check at `src/utterances/extractor.py:137`
(TASK-1488.05 will remove the inline check and call `classify_scrape()`
from the orchestrator).

Constraints:
- Pure function: no I/O, no mutation, no state.
- Deterministic: same input always yields the same output.
- Fixed-string `in` checks only — no regex (avoids ReDoS risk on
  attacker-controlled markup).
"""

from __future__ import annotations

from enum import StrEnum

from src.firecrawl_client import ScrapeResult


class ScrapeQuality(StrEnum):
    """Four outcomes of post-scrape quality classification.

    String values are stable for logging, metric labels, and DB
    persistence. See module docstring for priority ordering.
    """

    OK = "ok"
    INTERSTITIAL = "interstitial"
    AUTH_WALL = "auth_wall"
    LEGITIMATELY_EMPTY = "legitimately_empty"


# ---------------------------------------------------------------------------
# Heuristic constants — exported so test parameterization can iterate them
# rather than copy-paste literal strings (AC4).
# ---------------------------------------------------------------------------

AUTH_WALL_STATUS_CODES: frozenset[int] = frozenset({401, 403})
"""HTTP status codes that unambiguously indicate an auth wall.

403 may also appear from CF on a clean URL — but the priority order
(AUTH_WALL > INTERSTITIAL) is intentional: when in doubt, treat 403 as
terminal rather than escalating into interact-tier. False-negative on
auth bypass is a worse outcome than a false-negative on retry.
"""

AUTH_WALL_HTML_MARKERS: tuple[str, ...] = (
    'type="password"',
    "type='password'",
    'action="/login"',
    "action='/login'",
    'action="/signin"',
    "action='/signin'",
    'action="/sign-in"',
    "action='/sign-in'",
)
"""Fixed-string substrings indicating a login form is present in the HTML.

These markers are gated by the sparse-body check — see
:data:`SPARSE_BODY_THRESHOLD`. A login form embedded in a fully
rendered article (newsletter modal, signup CTA) is chrome, not gating.

TASK-1488.22 dropped six bare-URL substring markers (`/login"` and
friends) because they matched header navigation anchors on every site
that links to a login page, producing false positives like the Quizlet
blog incident (job c79722c2-...). Form-action variants stay because
the leading `action=` constrains the match to actual `<form>` elements.
"""

INTERSTITIAL_MARKERS: tuple[str, ...] = (
    "Just a moment",
    "cf-browser-verification",
    "Checking your browser",
    "challenge-platform",
    "Please enable JavaScript",
    "Please turn JavaScript on",
    "Enable JavaScript and reload",
    "__cf_chl_",
    "cf-challenge",
    "DDoS protection by",
)
"""Fixed-string substrings indicating a JS/CF challenge interstitial.

CF wording has shifted over the years; the canonical "Just a moment"
title and `cf-browser-verification` div class are stable across
versions. JS-required noscript banners are grouped here because the
caller-side response (escalate to a JS-capable tier) is the same.
"""

LEGITIMATELY_EMPTY_MARKERS: tuple[str, ...] = (
    "Page not found",
    "page not found",
    "404 Not Found",
    "This post has been deleted",
    "This page has been removed",
    "Sorry, this page isn't available",
    "Sorry, this page isn’t available",  # noqa: RUF001
    "doesn't exist",
    "no longer available",
    "has been removed",
)
"""Fixed-string substrings indicating a 404/deleted/removed page.

Distinguished from AUTH_WALL because there's nothing to escalate to —
the page truly has no content. Distinguished from INTERSTITIAL because
no richer fetch tier will resurrect deleted content.
"""

LEGITIMATELY_EMPTY_STATUS_CODES: frozenset[int] = frozenset({404, 410})
"""Status codes that indicate the resource is gone."""

MIN_BODY_CHARS: int = 32
"""Minimum non-whitespace markdown chars before we trust a bundle as OK.

Below this we treat the bundle as empty unless markers say otherwise.
Tuned conservatively — a real article that scrapes to <32 chars is
almost certainly behind a wall, not a stub.
"""

SPARSE_BODY_THRESHOLD: int = 500
"""Markdown char count below which login-form markers gate AUTH_WALL.

Tuned at "a few tweets worth" (~2 full tweets at 280 chars) — generous
enough that any real article exceeds it, tight enough that login-only
pages with their typical "Sign in to continue / Welcome back" prose
stay under it. Above this threshold a login-form marker is treated as
chrome (newsletter signup, footer login modal) rather than gating.
"""


# ---------------------------------------------------------------------------
# Public classifier.
# ---------------------------------------------------------------------------


def classify_scrape(result: ScrapeResult) -> ScrapeQuality:  # noqa: PLR0911
    """Classify a scraped page into AUTH_WALL / INTERSTITIAL / LEGITIMATELY_EMPTY / OK.

    Priority order (first match wins):

        1. AUTH_WALL          — login forms, redirect-to-login, 401/403.
        2. INTERSTITIAL       — CF challenge / JS-required markers.
        3. LEGITIMATELY_EMPTY — 404, deleted, empty bundle.
        4. OK                 — anything else.

    Pure function. Accepts `CachedScrape` because it subclasses
    `ScrapeResult`; the same logic applies whether the bundle came from
    Firecrawl directly or from the Supabase cache.
    """
    metadata = result.metadata
    status_code = metadata.status_code if metadata is not None else None
    html = result.html or ""
    markdown = result.markdown or ""
    body_text = f"{markdown}\n{html}"

    # Tier 1: AUTH_WALL — load-bearing priority (see module docstring).
    # 401/403 fire unconditionally. Login-form markers only fire when the
    # body is sparse — TASK-1488.22 — to avoid false positives on
    # publicly readable articles that link to a login page from chrome.
    if status_code is not None and status_code in AUTH_WALL_STATUS_CODES:
        return ScrapeQuality.AUTH_WALL
    body_chars = len(markdown.strip())
    if body_chars < SPARSE_BODY_THRESHOLD and _contains_any(html, AUTH_WALL_HTML_MARKERS):
        return ScrapeQuality.AUTH_WALL

    # Tier 2: INTERSTITIAL — CF / JS-required markers in markdown OR html.
    if _contains_any(body_text, INTERSTITIAL_MARKERS):
        return ScrapeQuality.INTERSTITIAL

    # Tier 3: LEGITIMATELY_EMPTY — explicit 'gone' markers, status code,
    # or empty/whitespace-only bundle. Empty-without-evidence is legit
    # rather than interstitial: no marker means no reason to escalate.
    if status_code is not None and status_code in LEGITIMATELY_EMPTY_STATUS_CODES:
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if _contains_any(body_text, LEGITIMATELY_EMPTY_MARKERS):
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if not markdown.strip() and not html.strip():
        return ScrapeQuality.LEGITIMATELY_EMPTY
    if len(markdown.strip()) < MIN_BODY_CHARS and not html.strip():
        return ScrapeQuality.LEGITIMATELY_EMPTY

    return ScrapeQuality.OK


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    """Fixed-string `in` over a tuple of markers — no regex.

    Cheap to evaluate and immune to ReDoS on attacker-controlled markup.
    Markers are author-curated; case sensitivity is intentional so that
    e.g. `"login"` in user-content prose doesn't trip AUTH_WALL.
    """
    return any(needle in haystack for needle in needles)
