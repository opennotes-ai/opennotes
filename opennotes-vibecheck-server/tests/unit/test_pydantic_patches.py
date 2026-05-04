from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch


def _reset_patch() -> None:
    """Remove the _repaired marker so each test starts from an unpatched state."""
    try:
        from pydantic_ai.tool_manager import ToolManager

        original = getattr(ToolManager, "_validate_tool_args")
        if getattr(original, "_repaired", False):
            wrapped = getattr(ToolManager, "__validate_tool_args_original__", None)
            if wrapped is not None:
                ToolManager._validate_tool_args = wrapped
                del ToolManager.__validate_tool_args_original__
    except Exception:
        pass


def setup_function() -> None:
    _reset_patch()


def teardown_function() -> None:
    _reset_patch()


class TestPatchIdempotency:
    def test_applying_patch_twice_does_not_double_wrap(self) -> None:
        from src.services.pydantic_patches import apply_all_patches
        from pydantic_ai.tool_manager import ToolManager

        apply_all_patches()
        first_patched = ToolManager._validate_tool_args

        apply_all_patches()
        second_patched = ToolManager._validate_tool_args

        assert first_patched is second_patched, (
            "apply_all_patches() must be idempotent: calling twice must not re-wrap"
        )
        assert getattr(ToolManager._validate_tool_args, "_repaired", False), (
            "_repaired sentinel must be True after patching"
        )


class TestImportErrorSilentNoop:
    def test_import_error_on_fast_json_repair_does_not_crash(self) -> None:
        fake_modules: dict[str, ModuleType | None] = {"fast_json_repair": None}
        with patch.dict(sys.modules, fake_modules):
            from src.services.pydantic_patches import patch_tool_call_json_repair

            patch_tool_call_json_repair()

    def test_apply_all_patches_import_error_is_silent(self) -> None:
        fake_modules: dict[str, ModuleType | None] = {"fast_json_repair": None}
        with patch.dict(sys.modules, fake_modules):
            from src.services.pydantic_patches import apply_all_patches

            apply_all_patches()


class TestMalformedJsonRepaired:
    def test_malformed_json_args_repaired_before_underlying_validate(self) -> None:
        from src.services.pydantic_patches import apply_all_patches
        from pydantic_ai.tool_manager import ToolManager

        apply_all_patches()

        received_args: list[str] = []

        async def _capture_original(
            self: object,
            call: object,
            tool: object,
            ctx: object,
            *,
            allow_partial: bool,
            args_override: object = None,
        ) -> dict:
            received_args.append(str(call.args))  # type: ignore[union-attr]
            return {}

        original_attr = getattr(ToolManager, "__validate_tool_args_original__", None)
        assert original_attr is not None, (
            "__validate_tool_args_original__ must be stored by the patch"
        )

        import asyncio

        malformed = '{"foo":"bar",}'

        call = MagicMock()
        call.args = malformed

        tool = MagicMock()
        ctx = MagicMock()

        with patch.object(
            ToolManager,
            "__validate_tool_args_original__",
            new=_capture_original,
        ):
            asyncio.run(
                ToolManager._validate_tool_args(
                    MagicMock(),
                    call,
                    tool,
                    ctx,
                    allow_partial=False,
                )
            )

        assert len(received_args) == 1
        repaired = received_args[0]
        assert repaired != malformed, f"Expected repaired args, got original: {repaired!r}"
        assert "foo" in repaired


class TestValidJsonPassesThrough:
    def test_valid_json_args_pass_through_unchanged(self) -> None:
        from src.services.pydantic_patches import apply_all_patches
        from pydantic_ai.tool_manager import ToolManager

        apply_all_patches()

        received_args: list[str] = []

        async def _capture_original(
            self: object,
            call: object,
            tool: object,
            ctx: object,
            *,
            allow_partial: bool,
            args_override: object = None,
        ) -> dict:
            received_args.append(str(call.args))  # type: ignore[union-attr]
            return {}

        import asyncio

        valid = '{"url": "https://example.com", "title": "Test"}'

        call = MagicMock()
        call.args = valid

        tool = MagicMock()
        ctx = MagicMock()

        with patch.object(
            ToolManager,
            "__validate_tool_args_original__",
            new=_capture_original,
        ):
            asyncio.run(
                ToolManager._validate_tool_args(
                    MagicMock(),
                    call,
                    tool,
                    ctx,
                    allow_partial=False,
                )
            )

        assert len(received_args) == 1
        assert received_args[0] == valid, (
            f"Structurally valid JSON must pass through unchanged, got: {received_args[0]!r}"
        )
