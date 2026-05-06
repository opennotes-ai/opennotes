# Archive Sanitizer Investigation

## Data Flow

Archived HTML reaches the analyze view through three paths:

1. Firecrawl URL scrapes are cached in `vibecheck_scrapes`. Cache writes call `strip_for_display`, which removes scripts and comments while preserving `<style>` and `<link>` tags for archived rendering (`src/cache/scrape_cache.py:121`, `src/utils/html_sanitize.py:45`).
2. The archive preview route first serves cached HTML when available, then falls back to a fresh Firecrawl `scrape(..., formats=["html"], only_main_content=True)` and stores the result before rendering it (`src/routes/frame.py:540`, `src/routes/frame.py:559`, `src/routes/frame.py:573`). Fresh-generation output is also passed through `strip_for_display` before response (`src/routes/frame.py:579`).
3. Browser-submitted HTML from the extension is sanitized with `strip_for_display` before storage, while markdown fallback generation uses `strip_for_llm` so stylesheet text does not enter model input (`src/routes/scrape.py:294`, `src/routes/scrape.py:297`). PDF extraction keeps model-input sanitation separate with `strip_for_llm` (`src/jobs/pdf_extract.py:45`).

The web app proxies archive responses through `/api/archive-preview`, injects the archive font fallback, and returns a restrictive CSP that allows inline and HTTPS styles but no scripts or nested frames (`opennotes-vibecheck-web/src/routes/api/archive-preview.ts:8`, `opennotes-vibecheck-web/src/routes/api/archive-preview.ts:20`, `opennotes-vibecheck-web/src/routes/api/archive-preview.ts:94`). The analyze page renders that proxy URL inside the archived iframe with `sandbox="allow-same-origin"` (`opennotes-vibecheck-web/src/components/PageFrame.tsx:348`).

Extractor and LLM paths intentionally keep the old aggressive cleanup: `strip_for_llm` removes scripts, styles, links, and comments (`src/utils/html_sanitize.py:55`). The utterance extractor uses that variant before media attribution and model input (`src/utterances/extractor.py:278`).

## Root Cause

The old single sanitizer removed `<script>`, `<style>`, `<link>`, and HTML comments for every caller. That was appropriate for LLM input, but it was too destructive for display archives. Pages that size images through inline CSS or linked stylesheets lost the declarations during cache write or fresh archive generation, so the archived iframe fell back to intrinsic image dimensions.

The reproduction is now captured in two layers:

- Unit coverage in `tests/unit/test_html_sanitize.py` proves `strip_for_display` preserves stylesheets while `strip_for_llm` keeps the prior stripping behavior.
- Playwright coverage in `opennotes-vibecheck-web/tests/e2e/archive-image-sizing.spec.ts` renders a blocked analyze-page fixture through the web archive proxy and archived iframe. The fixture asserts a 200x150 image sized by external CSS and a 300x200 image sized by inline CSS.

## Alternatives Surveyed

| Tool | Fit | Tradeoff |
| --- | --- | --- |
| SingleFile | Good fit for fully self-contained offline archives. | Heavier browser-style snapshot pipeline and larger blast radius than needed for preserving existing CSS tags. |
| Monolith | Good fit for CLI-produced self-contained HTML snapshots. | Fewer browser features than SingleFile and still a new archive generation path to operate. |
| Firecrawl options | Already in the scrape stack. | `formats=["html"]` returns HTML, but Firecrawl does not inline all style assets for us. |
| trafilatura | Good content extractor. | Wrong abstraction for archive fidelity because it discards page structure and styling. |

## Decision

Use two sanitizers instead of swapping archivers:

- `strip_for_display` removes executable/comment noise and preserves stylesheets for archived rendering.
- `strip_for_llm` preserves the previous model-input behavior.

This keeps the change small, matches the existing BeautifulSoup parser hardening, and avoids bespoke CSS preservation logic. Security remains concentrated in the iframe sandbox and archive CSP, which already disallow scripts and nested frames while allowing the styles needed for display fidelity. Cache TTL is short enough that no backfill is required; old broken cache rows age out naturally.
