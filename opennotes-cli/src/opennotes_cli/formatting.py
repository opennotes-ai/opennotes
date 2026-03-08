from __future__ import annotations

import uuid as uuid_mod

import click
import huuid


def truncate_uuid(uuid_str: str, prefix_len: int = 3, tail_len: int = 9) -> str:
    if len(uuid_str) <= prefix_len + tail_len + 1:
        return uuid_str
    return f"{uuid_str[:prefix_len]}\u2026{uuid_str[-tail_len:]}"


def resolve_id(value: str) -> str:
    try:
        return str(uuid_mod.UUID(value))
    except ValueError:
        pass
    try:
        return str(huuid.human2uuid(value))
    except (ValueError, TypeError):
        raise click.BadParameter(f"Invalid ID: '{value}'. Expected a UUID or huuid.")


def format_id(uuid_str: str, use_huuid: bool) -> str:
    if not use_huuid:
        return uuid_str
    try:
        return huuid.uuid2human(uuid_mod.UUID(uuid_str))
    except (ValueError, TypeError):
        return uuid_str
