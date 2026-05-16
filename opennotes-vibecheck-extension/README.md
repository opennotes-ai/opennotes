# Vibecheck Submitter

Minimal internal Chrome extension for submitting the current page HTML to a Vibecheck `/api/scrape` endpoint. It is intended for auth-gated pages that the server-side scraper cannot access.

## Load Unpacked

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select this `opennotes-vibecheck-extension` directory.

## Configure

Open the extension popup and set:

- Endpoint URL: the Vibecheck base URL, such as `http://localhost:3000` for local development or `https://vibecheck.opennotes.ai` for production. A full URL ending in `/api/scrape` is also accepted. Non-local endpoints must use HTTPS.
- API key: the bearer token configured on the server with `VIBECHECK_SCRAPE_API_TOKEN`.

Settings are stored in `chrome.storage.sync`.

On first submit to an endpoint origin, Chrome may ask you to grant the extension access to that origin so the popup can POST to `/api/scrape`.

## Submit A Page

1. Navigate to the page to submit.
2. Open the extension popup.
3. Confirm the current page URL.
4. Click Submit.

The extension captures `document.documentElement.outerHTML`, `document.title`, and `og:description` or `meta[name="description"]`, then posts:

```json
{
  "url": "https://example.com/article",
  "source_url": "https://example.com/article",
  "html": "<html>...</html>",
  "title": "Article title",
  "description": "Article summary",
  "screenshot_base64": "iVBORw0KGgo..."
}
```

The screenshot is a full-page PNG captured through Chrome debugger protocol. The field is omitted when capture fails or when the base64 PNG is larger than 20MB, so restricted pages such as `chrome://` URLs still submit without a screenshot. Chrome shows a temporary DevTools debugging banner while capture is active.

Successful responses display the returned `analyze_url` as a link.

## Comment Expansion

The popup includes an **Expand all comments** checkbox below Submit. The preference is stored in `chrome.storage.sync` as `vibecheck_expand_all_comments`.

When enabled, the extension injects comment-expansion scripts before it captures page HTML and the screenshot. Supported sites are Reddit, old Reddit, YouTube, TikTok, X/Twitter, and LinkedIn. Unsupported sites silently skip expansion and do not show a status box.

Expansion is capped at 50 click iterations and 25 seconds. If some work completes but a cap is hit, the popup shows `Expanding comments was partially successful` below the result. If expansion fails twice before doing useful work, the popup shows `Expanding comments was not successful`; submission still proceeds with the captured page.

## Screenshot Verification

1. Load this directory as an unpacked extension.
2. Configure the endpoint URL and API key.
3. Open a long HTTP(S) page.
4. Click Submit and confirm Chrome briefly shows the debugger banner.
5. Open the returned analyze URL.
6. Click Archived and confirm the archived pageframe shows the submitted page screenshot.

Known caveats:

- `chrome://`, Chrome Web Store, and other restricted browser pages reject debugger attachment; submission continues without `screenshot_base64`.
- Very large screenshots are dropped client-side at 20MB base64 size to avoid failing the submission.
