"""Monkey-patches for pydantic-ai internals.

patch_tool_call_json_repair: Patches ToolManager._validate_tool_args to repair
malformed JSON args via fast-json-repair before validation.

Covers STRUCTURAL JSON corruption only (trailing commas, unquoted keys,
unclosed brackets). Does NOT fix semantic field-value corruption like the
timestamp-leak observed in TASK-1527 — that bug is addressed by raising
pydantic-ai retries=3 in build_agent (TASK-1527.01), not this patch.
"""

from __future__ import annotations


def patch_tool_call_json_repair() -> None:
    try:
        from fast_json_repair import repair_json
        from pydantic_ai.tool_manager import ToolManager
    except ImportError:
        return

    if getattr(ToolManager._validate_tool_args, "_repaired", False):
        return

    _original = ToolManager._validate_tool_args
    ToolManager.__validate_tool_args_original__ = _original  # pyright: ignore[reportAttributeAccessIssue]

    async def _patched(
        self,
        call,
        tool,
        ctx,
        *,
        allow_partial: bool,
        args_override=None,
    ):
        if isinstance(call.args, str) and call.args:
            try:
                repaired = repair_json(call.args)
                if repaired != call.args:
                    call.args = repaired
            except Exception:
                pass
        original = ToolManager.__validate_tool_args_original__  # pyright: ignore[reportAttributeAccessIssue]
        return await original(
            self,
            call,
            tool,
            ctx,
            allow_partial=allow_partial,
            args_override=args_override,
        )

    _patched._repaired = True  # pyright: ignore[reportFunctionMemberAccess]
    ToolManager._validate_tool_args = _patched  # type: ignore[method-assign]


def apply_all_patches() -> None:
    patch_tool_call_json_repair()
