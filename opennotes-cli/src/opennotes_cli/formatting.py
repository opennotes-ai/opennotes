from __future__ import annotations

import uuid as uuid_mod

import click
import huuid


def resolve_id(value: str) -> str:
    try:
        return str(uuid_mod.UUID(value))
    except ValueError:
        pass
    try:
        return str(huuid.human2uuid(value))
    except (ValueError, TypeError):
        raise click.BadParameter(f"Invalid ID: '{value}'. Expected a UUID or huuid.")


def format_id(uuid_str: str | None, use_huuid: bool) -> str:
    if uuid_str is None:
        return "N/A"
    if not use_huuid:
        return uuid_str
    try:
        return huuid.uuid2human(uuid_mod.UUID(uuid_str))
    except (ValueError, TypeError):
        return uuid_str
