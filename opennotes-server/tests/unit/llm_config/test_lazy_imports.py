from __future__ import annotations

import importlib
from unittest.mock import patch

import src.llm_config as llm_config_mod


class TestLazyImportCaching:
    def _clear_cached(self, name: str) -> object | None:
        return llm_config_mod.__dict__.pop(name, None)

    def test_getattr_caches_in_globals(self) -> None:
        self._clear_cached("LLMService")

        assert "LLMService" not in llm_config_mod.__dict__

        _ = llm_config_mod.LLMService

        assert "LLMService" in llm_config_mod.__dict__

    def test_second_access_skips_import(self) -> None:
        self._clear_cached("LLMService")

        _ = llm_config_mod.LLMService

        original_import = importlib.import_module
        with patch.object(importlib, "import_module", wraps=original_import) as mock_import:
            _ = llm_config_mod.LLMService
            mock_import.assert_not_called()

    def test_all_lazy_imports_consistent_with_all(self) -> None:
        for name in llm_config_mod.__all__:
            assert name in llm_config_mod._LAZY_IMPORTS, (
                f"{name!r} is in __all__ but not in _LAZY_IMPORTS"
            )

    def test_all_lazy_imports_resolvable(self) -> None:
        for name in llm_config_mod._LAZY_IMPORTS:
            self._clear_cached(name)
            val = getattr(llm_config_mod, name)
            assert val is not None, f"Lazy import {name!r} resolved to None"

    def test_unknown_attr_raises(self) -> None:
        import pytest

        with pytest.raises(AttributeError, match="no attribute"):
            _ = llm_config_mod.NonExistentAttribute

    def test_router_in_lazy_imports(self) -> None:
        self._clear_cached("router")
        router = llm_config_mod.router
        assert router is not None
        assert "router" in llm_config_mod.__dict__
