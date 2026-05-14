from __future__ import annotations

import importlib
import inspect
from types import ModuleType

from pydantic_ai import Agent, Embedder
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider


def test_pydantic_ai_runtime_imports_resolve() -> None:
    direct = importlib.import_module("pydantic_ai.direct")

    assert isinstance(direct, ModuleType)
    assert inspect.isclass(Agent)
    assert inspect.isclass(Embedder)
    assert inspect.isclass(GoogleModel)
    assert inspect.isclass(GoogleProvider)


def test_vibecheck_pydantic_ai_modules_import_without_dev_only_dependencies() -> None:
    modules = [
        "src.analyses.claims.facts_agent",
        "src.services.embeddings",
        "src.services.gemini_agent",
        "src.utterances.extractor",
    ]

    for module_name in modules:
        module = importlib.import_module(module_name)
        assert isinstance(module, ModuleType), module_name
