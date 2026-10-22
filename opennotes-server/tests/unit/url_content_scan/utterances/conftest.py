from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.utils.url_security._resolve",
        lambda hostname: ["93.184.216.34"],
    )
