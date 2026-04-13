import importlib.util
import sys
import types
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "fixtures"


def _ensure_namespace(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


def _register_module(module_alias: str, file_path: Path) -> None:
    if module_alias in sys.modules:
        return
    parts = module_alias.split(".")
    for i in range(1, len(parts)):
        _ensure_namespace(".".join(parts[:i]))
    spec = importlib.util.spec_from_file_location(module_alias, file_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_alias] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]


_register_module(
    "opennotes_scripts.fixtures.anonymization_rules",
    _FIXTURES_DIR / "anonymization_rules.py",
)
_register_module(
    "opennotes_scripts.fixtures.generate_greenmask_config",
    _FIXTURES_DIR / "generate_greenmask_config.py",
)
