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
  "description": "Article summary"
}
```

Successful responses display the returned `analyze_url` as a link.
