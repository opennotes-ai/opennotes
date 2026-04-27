"""Live end-to-end verification of the /scrape -> /interact ladder.

TASK-1488.07 — exercises the real `_scrape_step` orchestrator helper
(via `_run_tier1` / `_run_tier2`) against the live Firecrawl API for a
fixed set of public URLs. Stubs the Supabase scrape cache with an
in-memory implementation so the run does not require a database, but
keeps every other moving part — refusal detection, classify_scrape,
TerminalError raising, span attributes — pristine.

Run::

    cd opennotes-vibecheck-server
    FIRECRAWL_API_KEY=fc-... uv run python scripts/run_ladder_e2e.py

Public URLs only. Budget capped at <=20 Firecrawl calls total
(four URLs * up to two tiers = eight expected calls in the happy path).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cache.scrape_cache import CachedScrape  # noqa: E402
from src.firecrawl_client import FirecrawlClient, ScrapeResult  # noqa: E402
from src.jobs.orchestrator import (  # noqa: E402
    TerminalError,
    TransientError,
    _scrape_step,
)


class InMemoryScrapeCache:
    """Drop-in stub for `SupabaseScrapeCache` with no DB dependency.

    Mirrors the test fixture in `tests/unit/test_orchestrator.py` so the
    orchestrator's cache contract is exercised honestly: keyed by
    (url, tier), get returns None on miss, put returns a CachedScrape.
    """

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], CachedScrape] = {}
        self.gets: list[tuple[str, str]] = []
        self.puts: list[tuple[str, str]] = []

    async def get(
        self, url: str, *, tier: str = "scrape"
    ) -> CachedScrape | None:
        self.gets.append((url, tier))
        return self.store.get((url, tier))

    async def put(
        self, url: str, scrape: ScrapeResult, *, tier: str = "scrape"
    ) -> CachedScrape:
        self.puts.append((url, tier))
        cached = CachedScrape(
            markdown=scrape.markdown,
            html=scrape.html,
            raw_html=scrape.raw_html,
            screenshot=scrape.screenshot,
            links=scrape.links,
            metadata=scrape.metadata,
            warning=scrape.warning,
            storage_key=None,
        )
        self.store[(url, tier)] = cached
        return cached

    async def evict(self, url: str, *, tier: str | None = None) -> None:
        return None


@dataclass
class CaseResult:
    label: str
    url: str
    outcome: str
    detail: str
    elapsed_s: float
    cache_puts: list[tuple[str, str]]
    markdown_len: int
    error_code: str | None


URL_CASES: list[tuple[str, str, str]] = [
    (
        "linkedin",
        "https://www.linkedin.com/posts/williamhgates_climate-action-activity-7000000000000000000",
        "expected: terminal UNSUPPORTED_SITE",
    ),
    (
        "reddit",
        "https://www.reddit.com/r/programming/comments/1bbmdg7/the_grug_brained_developer/",
        "expected: success via /interact",
    ),
    (
        "cf_blog",
        "https://www.g2.com/products/notion/reviews",
        "expected: success via /interact (Cloudflare-protected)",
    ),
    (
        "normal",
        "https://blog.cloudflare.com/page-rules-deprecation/",
        "expected: Tier 1 OK, no escalation",
    ),
    (
        "normal_alt",
        "https://en.wikipedia.org/wiki/Web_scraping",
        "alt normal: Wikipedia article (well-formed metadata)",
    ),
]


async def _run_one(
    label: str,
    url: str,
    note: str,
    *,
    api_key: str,
    budget: dict[str, int],
) -> CaseResult:
    if budget["remaining"] <= 0:
        return CaseResult(
            label=label,
            url=url,
            outcome="skipped",
            detail="firecrawl call budget exhausted",
            elapsed_s=0.0,
            cache_puts=[],
            markdown_len=0,
            error_code=None,
        )

    print(f"\n=== {label}: {url}")
    print(f"    note: {note}")

    cache = InMemoryScrapeCache()
    scrape_client = FirecrawlClient(api_key=api_key, max_attempts=1)
    interact_client = FirecrawlClient(api_key=api_key, max_attempts=2)

    started = time.monotonic()
    outcome = "ok"
    detail = ""
    markdown_len = 0
    error_code: str | None = None
    try:
        cached = await _scrape_step(
            url, scrape_client, interact_client, cache
        )
        markdown_len = len(cached.markdown or "")
        detail = f"Tier success → markdown={markdown_len} chars"
    except TerminalError as exc:
        outcome = "terminal"
        error_code = str(exc.error_code)
        detail = f"TerminalError({exc.error_code}): {exc.error_detail}"
    except TransientError as exc:
        outcome = "transient"
        detail = f"TransientError: {exc}"
    except Exception as exc:
        outcome = "unexpected"
        detail = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - started

    print(f"    outcome: {outcome}")
    print(f"    detail:  {detail}")
    print(f"    elapsed: {elapsed:.2f}s")
    print(f"    cache puts: {cache.puts}")

    # Budget accounting: Tier 1 always at most one call; Tier 2 may add up
    # to two attempts (max_attempts=2) for non-refusal upstream errors.
    consumed = 1
    if any(t == "interact" for _, t in cache.puts):
        consumed += 1
    elif outcome == "terminal" and "tier 2" in detail.lower():
        consumed += 1
    budget["remaining"] -= consumed
    print(f"    firecrawl calls (est.): {consumed} (remaining budget: {budget['remaining']})")

    return CaseResult(
        label=label,
        url=url,
        outcome=outcome,
        detail=detail,
        elapsed_s=elapsed,
        cache_puts=list(cache.puts),
        markdown_len=markdown_len,
        error_code=error_code,
    )


def _format_summary(results: list[CaseResult]) -> str:
    lines = [
        "| Label | URL | Outcome | Tier 2? | Final | Latency | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        tier2 = "yes" if any(t == "interact" for _, t in r.cache_puts) else (
            "yes" if r.outcome == "terminal" and "tier 2" in r.detail.lower() else "no"
        )
        final = r.error_code or (
            "OK" if r.outcome == "ok" else r.outcome
        )
        notes = r.detail.replace("|", "/")[:140]
        lines.append(
            f"| {r.label} | {r.url[:60]}... | {r.outcome} | {tier2} | {final} | {r.elapsed_s:.1f}s | {notes} |"
        )
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated subset: linkedin,reddit,cf_blog,normal")
    parser.add_argument("--budget", type=int, default=20, help="max firecrawl calls")
    parser.add_argument("--out", default="/tmp/ladder-e2e.json")
    args = parser.parse_args()

    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        print("FATAL: FIRECRAWL_API_KEY not set", file=sys.stderr)
        return 2

    selected = URL_CASES
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        selected = [c for c in URL_CASES if c[0] in wanted]

    budget = {"remaining": args.budget}
    results: list[CaseResult] = []
    for label, url, note in selected:
        results.append(
            await _run_one(label, url, note, api_key=api_key, budget=budget)
        )

    print("\n=== SUMMARY ===")
    print(_format_summary(results))

    payload = {
        "results": [
            {
                "label": r.label,
                "url": r.url,
                "outcome": r.outcome,
                "detail": r.detail,
                "elapsed_s": r.elapsed_s,
                "cache_puts": r.cache_puts,
                "markdown_len": r.markdown_len,
                "error_code": r.error_code,
            }
            for r in results
        ],
        "budget_remaining": budget["remaining"],
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
