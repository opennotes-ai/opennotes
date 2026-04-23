import pytest

from src.config import Settings, get_settings


def test_defaults():
    s = Settings()
    assert s.MAX_IMAGES_MODERATED == 30
    assert s.MAX_VIDEOS_MODERATED == 5
    assert s.WEB_RISK_CACHE_TTL_HOURS == 6


def test_max_images_moderated_env_override(monkeypatch):
    monkeypatch.setenv("MAX_IMAGES_MODERATED", "50")
    get_settings.cache_clear()
    try:
        assert get_settings().MAX_IMAGES_MODERATED == 50
    finally:
        get_settings.cache_clear()


def test_max_videos_moderated_env_override(monkeypatch):
    monkeypatch.setenv("MAX_VIDEOS_MODERATED", "20")
    get_settings.cache_clear()
    try:
        assert get_settings().MAX_VIDEOS_MODERATED == 20
    finally:
        get_settings.cache_clear()


def test_web_risk_cache_ttl_env_override(monkeypatch):
    monkeypatch.setenv("WEB_RISK_CACHE_TTL_HOURS", "12")
    get_settings.cache_clear()
    try:
        assert get_settings().WEB_RISK_CACHE_TTL_HOURS == 12
    finally:
        get_settings.cache_clear()
