from __future__ import annotations

from starlette.requests import Request

from src.config import get_settings
from src.routes._rate_limit_keys import (
    hashed_ip_and_job_id_key,
    hashed_remote_address,
    server_poll_rate_key,
    server_retry_rate_key,
    server_submit_rate_key,
)


def _request(host: str = "203.0.113.10", job_id: str | None = "job-123") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/analyze/job-123",
        "headers": [],
        "client": (host, 4321),
        "path_params": {},
    }
    if job_id is not None:
        scope["path_params"] = {"job_id": job_id}
    return Request(scope)


def test_hashed_remote_address_is_deterministic(monkeypatch):
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-a")
    get_settings.cache_clear()
    try:
        request = _request()
        assert hashed_remote_address(request) == hashed_remote_address(request)
        assert len(hashed_remote_address(request)) == 16
        assert "203.0.113.10" not in hashed_remote_address(request)
    finally:
        get_settings.cache_clear()


def test_hashed_remote_address_changes_with_salt(monkeypatch):
    request = _request()
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-a")
    get_settings.cache_clear()
    first = hashed_remote_address(request)

    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-b")
    get_settings.cache_clear()
    second = hashed_remote_address(request)

    get_settings.cache_clear()
    assert first != second


def test_hashed_remote_address_uses_dev_sentinel_for_empty_salt(monkeypatch):
    monkeypatch.delenv("VIBECHECK_LIMITER_KEY_SALT", raising=False)
    get_settings.cache_clear()
    try:
        assert hashed_remote_address(_request()) == hashed_remote_address(_request())
        assert hashed_remote_address(_request()) != "203.0.113.10"
    finally:
        get_settings.cache_clear()


def test_hashed_ip_and_job_id_key_keeps_job_id_plain(monkeypatch):
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-a")
    get_settings.cache_clear()
    try:
        key = hashed_ip_and_job_id_key(_request(job_id="7f6d0f28"))
    finally:
        get_settings.cache_clear()

    hashed_ip, job_id = key.split(":", 1)
    assert len(hashed_ip) == 16
    assert job_id == "7f6d0f28"
    assert "203.0.113.10" not in key


def test_hashed_ip_and_job_id_key_matches_existing_missing_job_fallback(monkeypatch):
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-a")
    get_settings.cache_clear()
    try:
        key = hashed_ip_and_job_id_key(_request(job_id=None))
    finally:
        get_settings.cache_clear()

    assert key.endswith(":")
    assert len(key.split(":", 1)[0]) == 16


def test_server_route_keys_are_namespaced_and_never_include_raw_ip(monkeypatch):
    monkeypatch.setenv("VIBECHECK_LIMITER_KEY_SALT", "salt-a")
    get_settings.cache_clear()
    try:
        request = _request(job_id="job-123")
        submit_key = server_submit_rate_key(request)
        poll_key = server_poll_rate_key(request)
        retry_key = server_retry_rate_key(request)
    finally:
        get_settings.cache_clear()

    assert submit_key.startswith("vibecheck:rl:server:submit:")
    assert poll_key.startswith("vibecheck:rl:server:poll:")
    assert retry_key.startswith("vibecheck:rl:server:retry:")
    assert poll_key.endswith(":job-123")
    assert retry_key.endswith(":job-123")
    assert "203.0.113.10" not in f"{submit_key} {poll_key} {retry_key}"
