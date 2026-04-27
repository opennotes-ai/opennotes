# opennotes-vibecheck-web

SolidStart app for [vibecheck.opennotes.ai](https://vibecheck.opennotes.ai). Public site (no auth) that renders against `@opennotes/tokens` design tokens and the `opennotes-vibecheck-server` API. Run locally with `pnpm --filter opennotes-vibecheck-web dev` (port 3200); production builds ship via the Dockerfile on port 8080.

## Embed API: POST /embed/v1/start

Stable, versioned, no-JS form contract for marketing pages and any other opennotes.ai surface that wants to drop in a vibecheck submission widget.

### HTML snippet (paste-ready)

```html
<form action="https://vibecheck.opennotes.ai/embed/v1/start" method="post">
  <input
    name="url"
    type="url"
    inputmode="url"
    autocomplete="url"
    autocapitalize="none"
    spellcheck="false"
    required
    placeholder="https://example.com/article"
  />
  <button type="submit">Analyze</button>
</form>
```

No CORS preflight, no API key, no JavaScript. The browser follows the 303 redirect to the live job page on `vibecheck.opennotes.ai`.

### Contract

| Item | Value |
|---|---|
| URL | `https://vibecheck.opennotes.ai/embed/v1/start` |
| Method | `POST` (only) |
| Form encoding | `application/x-www-form-urlencoded` or `multipart/form-data` |
| Required field | `url` — an `http://` or `https://` URL |
| Success redirect | `303 See Other` to `/analyze?job=<id>` (with `&c=1` when cached) |
| Method rejection | `405 Method Not Allowed` with `Allow: POST` for any non-POST method |

### Redirect destinations

| Outcome | Status | Location |
|---|---|---|
| Fresh submit | 303 | `/analyze?job=<id>` |
| Cache hit | 303 | `/analyze?job=<id>&c=1` |
| Invalid URL | 303 | `/?error=invalid_url` |
| Unsupported site | 303 | `/analyze?pending_error=unsupported_site&url=<x>&host=<h>` |
| Per-IP rate limit hit | 303 | `/analyze?pending_error=rate_limited&url=<x>` |
| Other backend error | 303 | `/analyze?pending_error=<code>&url=<x>` |

### Why POST-only

`GET` would let link previewers, crawlers, browser prefetchers, and unauthenticated `<a href>` clicks silently mint analysis jobs. The endpoint rejects non-POST with `405 Method Not Allowed` and `Allow: POST` to make the contract explicit.

### Why no CORS / Origin allowlist

Cross-origin form POST is allowed by browsers without preflight (form-encoded request bodies don't require it). The endpoint is intentionally permissive for cross-origin form submission — that's the point of the embed surface. No `Access-Control-Allow-Origin` header is set, no `Origin` header is checked. This is by design; future security review should not flag this as a bug.

### Rate limiting

Submissions are rate-limited per real client IP at the web tier — extracted from the GCLB-set `X-Forwarded-For` header (TASK-1483.09). Default budget is 30 submissions per IP per hour. When exceeded, the endpoint redirects to `/analyze?pending_error=rate_limited&url=<x>`. The limit is configurable via the `VIBECHECK_RATE_LIMIT_PER_HOUR` environment variable; the limiter is disabled in non-production environments and can be force-disabled with `VIBECHECK_RATE_LIMIT_DISABLED=1`.

### Versioning policy

`/embed/v1/start` is supported indefinitely once shipped. Breaking changes go to `/embed/v2/start`. Embedded marketing pages and external integrations should always reference the versioned path — never link to unversioned routes (e.g. the home form action).
