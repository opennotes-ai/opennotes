# opennotes-vibecheck-server

FastAPI backend for [vibecheck.opennotes.ai](https://vibecheck.opennotes.ai): a lightweight URL claim-extraction and fact-check service that scrapes a URL with Firecrawl, extracts claims via DSPy/OpenAI, looks them up against Google Fact Check Tools, and caches results in Supabase. This scaffold is intentionally lean — no Alembic, no SQLAlchemy, no Logfire — see parent task [TASK-1471](../backlog/tasks/task-1471) for the broader plan.

## Quickstart

```bash
uv sync                          # install dependencies
cp .env.example .env             # fill in API keys
mise run dev                     # serve on http://localhost:8000 with auto-reload
mise run test                    # run the test suite
mise run build                   # build the production Docker image
```

Health check: `GET /health` returns `{"status": "ok"}`.
