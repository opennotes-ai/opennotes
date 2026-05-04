from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from src.config import Settings
from src.firecrawl_client import FirecrawlError, ScrapeResult
from src.jobs import pdf_extract
from src.utterances.errors import (
    TransientExtractionError,
    ZeroUtterancesError,
)
from src.utterances.schema import Utterance, UtterancesPayload


class FakeAcquire:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def __aenter__(self) -> Any:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakePool:
    def __init__(self, *, raise_on_execute: BaseException | None = None) -> None:
        self.conn = SimpleNamespace(executed=[])
        self._raise = raise_on_execute

        async def execute(query: str, *args: object) -> str:
            self.conn.executed.append((query, args))
            if self._raise is not None:
                raise self._raise
            return "INSERT 0 1"

        self.conn.execute = execute

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


class FakePdfStore:
    def __init__(self, bucket_name: str) -> None:
        assert bucket_name == "pdf-bucket"
        self.signed_read_calls: list[tuple[str, int]] = []

    def signed_read_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        # TASK-1498.27: TTL is bumped to 3600s so the URL outlives Firecrawl
        # queueing/processing time (worst case ~30 minutes).
        assert ttl_seconds == 3600
        self.signed_read_calls.append((key, ttl_seconds))
        return f"https://storage.example/{key}?signed=1"


class FakeScrapeCache:
    def __init__(self) -> None:
        self.puts: list[tuple[str, object]] = []

    async def put(self, url: str, scrape: object, **kwargs: object) -> object:
        self.puts.append((url, scrape))
        return scrape


class FakeClient:
    def __init__(self, result: ScrapeResult | BaseException) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def scrape(self, url: str, **kwargs: object) -> ScrapeResult:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _settings() -> Settings:
    return cast(
        Settings,
        SimpleNamespace(VIBECHECK_PDF_UPLOAD_BUCKET="pdf-bucket"),
    )


def _fake_store_factory(_bucket: str) -> FakePdfStore:
    return FakePdfStore("pdf-bucket")


async def test_pdf_extract_stores_html_and_extracts_from_signed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    gcs_key = uuid4().hex
    pool = FakePool()
    client = FakeClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )
    payload = UtterancesPayload(
        source_url=gcs_key,
        scraped_at=datetime.now(UTC),
        utterances=[
            Utterance(kind="post", text="Alice opens calmly."),
        ],
    )
    extract_calls: list[dict[str, object]] = []

    async def fake_extract_utterances(
        url: str,
        extract_client: object,
        scrape_cache: object,
        *,
        settings: object,
        scrape: object,
    ) -> UtterancesPayload:
        extract_calls.append(
            {
                "url": url,
                "client": extract_client,
                "scrape_cache": scrape_cache,
                "settings": settings,
                "scrape": scrape,
            }
        )
        return payload

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    scrape_cache = FakeScrapeCache()
    result = await pdf_extract.pdf_extract_step(
        pool,
        job_id,
        gcs_key,
        settings=_settings(),
        client=cast(Any, client),
        scrape_cache=cast(Any, scrape_cache),
    )

    assert result is payload
    assert client.calls == [
        {
            "url": f"https://storage.example/{gcs_key}?signed=1",
            "formats": ["html", "markdown"],
            "only_main_content": True,
        }
    ]
    assert len(pool.conn.executed) == 1
    _query, args = pool.conn.executed[0]
    assert args == (job_id, "<main><p>Alice opens calmly.</p></main>")
    assert extract_calls[0]["url"] == gcs_key
    cached = cast(Any, extract_calls[0]["scrape"])
    assert cached.markdown == "Alice opens calmly."
    assert cached.metadata.source_url == gcs_key
    # TASK-1498.16: scrape cache populated BEFORE archive write so retry
    # after a transient archive failure does not re-pay Firecrawl.
    assert len(scrape_cache.puts) == 1
    assert scrape_cache.puts[0][0] == gcs_key


async def test_pdf_extract_rejects_html_without_block_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()
    client = FakeClient(ScrapeResult(html="<span>tiny</span>", markdown="tiny"))
    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)

    with pytest.raises(
        pdf_extract.PDFExtractionError, match="no usable HTML"
    ):
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, FakeScrapeCache()),
        )

    assert pool.conn.executed == []


async def test_pdf_extract_preserves_retriable_firecrawl_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()
    client = FakeClient(FirecrawlError("rate limited", status_code=429))
    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)

    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, FakeScrapeCache()),
        )

    assert info.value.provider == "firecrawl"
    assert info.value.status_code == 429
    assert pool.conn.executed == []


async def test_pdf_extract_preserves_transient_utterance_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()
    client = FakeClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )

    async def fake_extract_utterances(*args: object, **kwargs: object) -> None:
        raise TransientExtractionError(
            provider="vertex",
            status_code=503,
            status="UNAVAILABLE",
            fallback_message="Vertex 503",
        )

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, FakeScrapeCache()),
        )

    assert info.value.provider == "vertex"
    assert len(pool.conn.executed) == 1


async def test_pdf_extract_archive_db_failure_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.16: A transient Postgres failure during the archive write
    must surface as TransientExtractionError so Cloud Tasks redelivers the
    job, instead of permanently failing a job whose content already extracted
    successfully."""
    pool = FakePool(raise_on_execute=RuntimeError("connection reset"))
    client = FakeClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )
    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)

    scrape_cache = FakeScrapeCache()
    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, scrape_cache),
        )

    assert info.value.provider == "postgres"
    assert "PDF archive write failed" in info.value.fallback_message
    # Cache write happened BEFORE the archive write, so the next retry
    # picks up the cached scrape rather than re-charging Firecrawl.
    assert len(scrape_cache.puts) == 1


async def test_pdf_extract_zero_utterances_is_terminal_pdf_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.17: ZeroUtterancesError is caught explicitly so the failure
    code distinguishes 'no utterances' from generic extraction failure, while
    still terminating as PDFExtractionError (no tier escalation for PDFs)."""
    pool = FakePool()
    client = FakeClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )

    async def fake_extract_utterances(*args: object, **kwargs: object) -> None:
        raise ZeroUtterancesError("Gemini returned 0 utterances")

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    with pytest.raises(pdf_extract.PDFExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, FakeScrapeCache()),
        )

    assert "zero utterances" in str(info.value)
    assert info.value.__cause__.__class__ is ZeroUtterancesError


async def test_pdf_extract_step_signed_url_minted_just_before_scrape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.27: The signed URL must be minted immediately before
    `client.scrape` (not at the start of the step) and must use a 1-hour TTL
    so the URL survives Firecrawl queue/processing time."""
    job_id = uuid4()
    gcs_key = uuid4().hex
    pool = FakePool()

    events: list[str] = []

    class TrackingFakePdfStore(FakePdfStore):
        def signed_read_url(
            self, key: str, *, ttl_seconds: int = 900
        ) -> str:
            events.append("signed_read_url")
            return super().signed_read_url(key, ttl_seconds=ttl_seconds)

    captured_stores: list[TrackingFakePdfStore] = []

    def tracking_factory(_bucket: str) -> TrackingFakePdfStore:
        store = TrackingFakePdfStore("pdf-bucket")
        captured_stores.append(store)
        return store

    class TrackingClient:
        def __init__(self, result: ScrapeResult) -> None:
            self.result = result
            self.calls: list[dict[str, object]] = []

        async def scrape(self, url: str, **kwargs: object) -> ScrapeResult:
            events.append("client.scrape")
            self.calls.append({"url": url, **kwargs})
            return self.result

    client = TrackingClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )

    payload = UtterancesPayload(
        source_url=gcs_key,
        scraped_at=datetime.now(UTC),
        utterances=[Utterance(kind="post", text="Alice opens calmly.")],
    )

    async def fake_extract_utterances(
        url: str,
        extract_client: object,
        scrape_cache: object,
        *,
        settings: object,
        scrape: object,
    ) -> UtterancesPayload:
        return payload

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", tracking_factory)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    result = await pdf_extract.pdf_extract_step(
        pool,
        job_id,
        gcs_key,
        settings=_settings(),
        client=cast(Any, client),
        scrape_cache=cast(Any, FakeScrapeCache()),
    )

    assert result is payload
    # Sign happens immediately before scrape (no other awaits in between).
    assert events.index("signed_read_url") + 1 == events.index("client.scrape")
    # And exactly one signing call with ttl_seconds=3600 (TASK-1498.27).
    assert len(captured_stores) == 1
    assert captured_stores[0].signed_read_calls == [(gcs_key, 3600)]


async def test_pdf_extract_step_cache_put_failure_raises_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-1498.31: A scrape_cache.put failure must surface as
    TransientExtractionError so the job is retried with a fresh Firecrawl
    call, instead of silently breaking the TASK-1498.16 'cache before
    archive' invariant."""
    pool = FakePool()
    client = FakeClient(
        ScrapeResult(
            html="<main><p>Alice opens calmly.</p></main>",
            markdown="Alice opens calmly.",
        )
    )

    class FailingScrapeCache:
        def __init__(self) -> None:
            self.puts: list[tuple[str, object]] = []

        async def put(
            self, url: str, scrape: object, **kwargs: object
        ) -> object:
            self.puts.append((url, scrape))
            raise RuntimeError("supabase write failed")

    extract_calls: list[object] = []

    async def fake_extract_utterances(*args: object, **kwargs: object) -> None:
        extract_calls.append(args)
        raise AssertionError(
            "extract_utterances must not run when cache put failed"
        )

    monkeypatch.setattr(pdf_extract, "get_pdf_upload_store", _fake_store_factory)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    scrape_cache = FailingScrapeCache()
    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, scrape_cache),
        )

    assert info.value.provider == "supabase"
    assert "cache put failed" in info.value.fallback_message.lower()
    # Cache put was attempted exactly once.
    assert len(scrape_cache.puts) == 1
    # Archive write was NOT attempted: we raise before that step so the retry
    # re-scrapes Firecrawl with integrity intact.
    assert pool.conn.executed == []
    # And extract_utterances was NOT invoked.
    assert extract_calls == []
