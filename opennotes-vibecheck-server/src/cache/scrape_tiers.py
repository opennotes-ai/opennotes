from __future__ import annotations

from typing import Literal

ScrapeTier = Literal["scrape", "interact", "browser_html", "x_api"]

# Shared URL-scoped rows are keyed by (normalized_url, tier). browser_html is
# job-scoped and intentionally excluded from these precedence lists.
URL_SCOPED_SCRAPE_TIERS: tuple[ScrapeTier, ...] = ("scrape", "interact", "x_api")
URL_SCOPED_EVICT_TIERS: tuple[ScrapeTier, ...] = ("scrape", "interact", "x_api")
ARCHIVE_CACHE_TIERS: tuple[ScrapeTier, ...] = ("interact", "x_api", "scrape")
RECENT_URL_TIER_PRIORITY: tuple[ScrapeTier, ...] = ("interact", "x_api", "scrape")


def sql_literal_list(tiers: tuple[ScrapeTier, ...]) -> str:
    return ", ".join(f"'{tier}'" for tier in tiers)


def sql_priority_case(alias: str, tiers: tuple[ScrapeTier, ...]) -> str:
    parts = " ".join(
        f"WHEN {alias}.tier = '{tier}' THEN {index}"
        for index, tier in enumerate(tiers)
    )
    return f"CASE {parts} ELSE {len(tiers)} END"
