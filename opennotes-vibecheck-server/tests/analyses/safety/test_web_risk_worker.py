"""Tests for src/analyses/safety/web_risk_worker.py (TASK-1474.11).

Monkeypatches `check_urls` — no real HTTP calls.
"""
from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID

import pytest

from src.analyses.safety._schemas import WebRiskFinding
from src.analyses.safety.web_risk import WebRiskTransientError
from src.config import Settings
from src.utterances.schema import Utterance, UtterancesPayload

_JOB_ID = UUID("018f0000-0000-7000-8000-000000000001")
_TASK_ATTEMPT = UUID("018f0000-0000-7000-8000-000000000002")


def _make_payload(
    source_url: str = "",
    utterances: list[Utterance] | None = None,
) -> UtterancesPayload:
    from datetime import datetime

    return UtterancesPayload(
        source_url=source_url,
        scraped_at=datetime.now(UTC),
        utterances=utterances or [],
    )


def _make_utterance(
    text: str = "hello",
    urls: list[str] | None = None,
    images: list[str] | None = None,
    videos: list[str] | None = None,
) -> Utterance:
    return Utterance(
        kind="post",
        text=text,
        mentioned_urls=urls or [],
        mentioned_images=images or [],
        mentioned_videos=videos or [],
    )


def _clean_findings(*urls: str) -> dict[str, WebRiskFinding]:
    return {u: WebRiskFinding(url=u, threat_types=[]) for u in urls}


def _threat_findings(*urls: str) -> dict[str, WebRiskFinding]:
    return {u: WebRiskFinding(url=u, threat_types=["MALWARE"]) for u in urls}


@pytest.mark.asyncio
async def test_no_utterances_returns_empty_findings_no_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[Any] = []

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        called.append(urls)
        return {}

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    payload = _make_payload(source_url="", utterances=[])
    result = await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())

    assert result == {"findings": []}
    assert called == []


@pytest.mark.asyncio
async def test_unifies_page_url_and_utterance_media_into_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_urls: list[list[str]] = []

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        received_urls.append(urls)
        return _clean_findings(*urls)

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from importlib import reload

    import src.analyses.safety.web_risk_worker as mod
    reload(mod)

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    utt = _make_utterance(
        urls=["https://example.com/link"],
        images=["https://img.example.com/a.jpg"],
        videos=["https://vid.example.com/b.mp4"],
    )
    payload = _make_payload(
        source_url="https://source.example.com/page",
        utterances=[utt],
    )

    result = await mod.run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())

    assert result == {"findings": []}
    assert len(received_urls) == 1
    pool = received_urls[0]
    assert sorted(pool) == pool
    assert "https://source.example.com/page" in pool
    assert "https://example.com/link" in pool
    assert "https://img.example.com/a.jpg" in pool
    assert "https://vid.example.com/b.mp4" in pool


@pytest.mark.asyncio
async def test_omits_clean_urls_from_output_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls_to_check = ["https://safe.example.com/a", "https://safe.example.com/b"]

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        return _clean_findings(*urls)

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    utt = _make_utterance(urls=urls_to_check)
    payload = _make_payload(utterances=[utt])

    result = await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())

    assert result == {"findings": []}


@pytest.mark.asyncio
async def test_includes_threatened_findings_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe_url = "https://safe.example.com/ok"
    bad_url = "https://malware.example.com/evil"

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        results: dict[str, WebRiskFinding] = {}
        for u in urls:
            if u == bad_url:
                results[u] = WebRiskFinding(url=u, threat_types=["MALWARE"])
            else:
                results[u] = WebRiskFinding(url=u, threat_types=[])
        return results

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    utt = _make_utterance(urls=[safe_url, bad_url])
    payload = _make_payload(utterances=[utt])

    result = await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())

    assert len(result["findings"]) == 1
    assert result["findings"][0]["url"] == bad_url
    assert result["findings"][0]["threat_types"] == ["MALWARE"]


@pytest.mark.asyncio
async def test_dedupes_url_across_text_image_video_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dup_url = "https://shared.example.com/resource"
    received: list[list[str]] = []

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        received.append(list(urls))
        return _clean_findings(*urls)

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    utt = _make_utterance(
        urls=[dup_url],
        images=[dup_url],
        videos=[dup_url],
    )
    payload = _make_payload(source_url=dup_url, utterances=[utt])

    result = await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())

    assert result == {"findings": []}
    assert len(received) == 1
    assert received[0].count(dup_url) == 1


@pytest.mark.asyncio
async def test_transient_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        raise WebRiskTransientError("503 upstream")

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    utt = _make_utterance(urls=["https://any.example.com/page"])
    payload = _make_payload(utterances=[utt])

    with pytest.raises(WebRiskTransientError, match="503 upstream"):
        await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, Settings())


@pytest.mark.asyncio
async def test_respects_web_risk_cache_ttl_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: list[dict[str, Any]] = []

    async def fake_check_urls(urls: list[str], **kwargs: Any) -> dict[str, WebRiskFinding]:
        captured_kwargs.append(dict(kwargs))
        return _clean_findings(*urls)

    monkeypatch.setattr("src.analyses.safety.web_risk_worker.check_urls", fake_check_urls)

    from src.analyses.safety.web_risk_worker import run_web_risk

    settings = Settings(WEB_RISK_CACHE_TTL_HOURS=42)
    utt = _make_utterance(urls=["https://ttl-test.example.com/page"])
    payload = _make_payload(utterances=[utt])

    await run_web_risk(None, _JOB_ID, _TASK_ATTEMPT, payload, settings)

    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["ttl_hours"] == 42
