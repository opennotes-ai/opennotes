from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from src.config import Settings
from src.firecrawl_client import FirecrawlError, ScrapeResult
from src.jobs import pdf_extract
from src.utterances.errors import TransientExtractionError
from src.utterances.schema import Utterance, UtterancesPayload


class FakeAcquire:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def __aenter__(self) -> Any:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakePool:
    def __init__(self) -> None:
        self.conn = SimpleNamespace(executed=[])

        async def execute(query: str, *args: object) -> str:
            self.conn.executed.append((query, args))
            return "INSERT 0 1"

        self.conn.execute = execute

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


class FakePdfStore:
    def __init__(self, bucket_name: str) -> None:
        assert bucket_name == "pdf-bucket"

    def signed_read_url(self, key: str, *, ttl_seconds: int = 900) -> str:
        assert ttl_seconds == 900
        return f"https://storage.example/{key}?signed=1"


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

    monkeypatch.setattr(pdf_extract, "PdfUploadStore", FakePdfStore)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    scrape_cache = object()
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


async def test_pdf_extract_rejects_html_without_block_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()
    client = FakeClient(ScrapeResult(html="<span>tiny</span>", markdown="tiny"))
    monkeypatch.setattr(pdf_extract, "PdfUploadStore", FakePdfStore)

    with pytest.raises(
        pdf_extract.PDFExtractionError, match="no usable HTML"
    ):
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, object()),
        )

    assert pool.conn.executed == []


async def test_pdf_extract_preserves_retriable_firecrawl_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = FakePool()
    client = FakeClient(FirecrawlError("rate limited", status_code=429))
    monkeypatch.setattr(pdf_extract, "PdfUploadStore", FakePdfStore)

    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, object()),
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

    monkeypatch.setattr(pdf_extract, "PdfUploadStore", FakePdfStore)
    monkeypatch.setattr(pdf_extract, "extract_utterances", fake_extract_utterances)

    with pytest.raises(TransientExtractionError) as info:
        await pdf_extract.pdf_extract_step(
            pool,
            uuid4(),
            uuid4().hex,
            settings=_settings(),
            client=cast(Any, client),
            scrape_cache=cast(Any, object()),
        )

    assert info.value.provider == "vertex"
    assert len(pool.conn.executed) == 1
