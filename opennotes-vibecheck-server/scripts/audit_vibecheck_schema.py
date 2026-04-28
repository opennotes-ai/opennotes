#!/usr/bin/env python
"""Audit `src/cache/schema.sql` against a live Vibecheck Supabase database.

Required env vars:
- VIBECHECK_SUPABASE_URL: canonical `https://<project-ref>.supabase.co` URL.
- VIBECHECK_SUPABASE_DB_PASSWORD: database password for the Supavisor user.
- VIBECHECK_DATABASE_HOST: Supavisor host for the target project.

Optional env vars:
- VIBECHECK_DATABASE_PORT: Supavisor port; defaults to 6543.

Exit codes:
- 0: no drift detected.
- 1: drift detected.
- 2: parse, connection, or audit execution failure.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg
import sqlparse

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "cache" / "schema.sql"
DEFAULT_POOLER_PORT = 6543
DEFAULT_TIMEOUT_SECONDS = 30.0

logger = logging.getLogger("audit_vibecheck_schema")

_IDENT = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
_QUALIFIED = rf"{_IDENT}(?:\.{_IDENT})?"


@dataclass(frozen=True)
class ColumnExpectation:
    name: str
    definition: str
    ordinal: int


@dataclass(frozen=True)
class ConstraintExpectation:
    name: str
    expression: str = ""


@dataclass
class TableExpectation:
    schema: str
    name: str
    defined: bool = True
    columns: list[ColumnExpectation] = field(default_factory=list)
    constraints: dict[str, ConstraintExpectation] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def columns_by_name(self) -> dict[str, ColumnExpectation]:
        return {column.name: column for column in self.columns}


@dataclass(frozen=True)
class IndexExpectation:
    schema: str
    name: str
    table: str
    unique: bool
    columns: tuple[str, ...]
    predicate: str = ""

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True)
class PolicyExpectation:
    name: str
    using: str = ""
    with_check: str = ""


@dataclass(frozen=True)
class FunctionExpectation:
    schema: str
    name: str
    identity_arguments: str
    owner: str = ""
    security_definer: bool = False
    search_path: tuple[str, ...] = ()
    grants: set[str] = field(default_factory=set)
    revokes: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.name}({self.identity_arguments})"


@dataclass
class ExpectedSchema:
    tables: dict[str, TableExpectation] = field(default_factory=dict)
    indexes: dict[str, IndexExpectation] = field(default_factory=dict)
    rls_enabled: set[str] = field(default_factory=set)
    rls_forced: set[str] = field(default_factory=set)
    policies: dict[str, dict[str, PolicyExpectation]] = field(default_factory=dict)
    cron_jobs: dict[str, str] = field(default_factory=dict)
    functions: dict[str, FunctionExpectation] = field(default_factory=dict)
    table_revokes: dict[str, set[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _compact(sql: str) -> str:
    return " ".join(sqlparse.format(sql, strip_comments=True).split())


def _unquote(identifier: str) -> str:
    value = identifier.strip().rstrip(";")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def _parse_name(identifier: str, default_schema: str = "public") -> tuple[str, str]:
    parts = [part.strip() for part in identifier.strip().rstrip(";").split(".", 1)]
    if len(parts) == 1:
        return default_schema, _unquote(parts[0])
    return _unquote(parts[0]), _unquote(parts[1])


def _qualified(schema: str, name: str) -> str:
    return f"{schema}.{name}"


def _normalize_expr(value: str) -> str:
    expr = " ".join(value.strip().rstrip(";").split())
    expr = re.sub(r"::[A-Za-z_][A-Za-z0-9_]*(?:\[\])?", "", expr)
    while expr.startswith("(") and expr.endswith(")") and _balanced(expr[1:-1]):
        expr = expr[1:-1].strip()
    return expr


def _normalize_type(value: str) -> str:
    normalized = " ".join(value.strip().rstrip(",").split()).upper()
    normalized = normalized.replace("CHARACTER VARYING", "VARCHAR")
    normalized = normalized.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ")
    return normalized.replace("INTEGER", "INT")


def _balanced(value: str) -> bool:
    depth = 0
    quote: str | None = None
    for char in value:
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and quote is None


def _split_csv(text: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    dollar_quote: str | None = None
    index = 0
    while index < len(text):
        if dollar_quote:
            if text.startswith(dollar_quote, index):
                current.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
                continue
            current.append(text[index])
            index += 1
            continue

        dollar_match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", text[index:])
        if not quote and dollar_match:
            dollar_quote = dollar_match.group(0)
            current.append(dollar_quote)
            index += len(dollar_quote)
            continue

        char = text[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        values.append(tail)
    return values


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    dollar_quote: str | None = None
    index = open_index
    while index < len(text):
        if dollar_quote:
            if text.startswith(dollar_quote, index):
                index += len(dollar_quote)
                dollar_quote = None
                continue
            index += 1
            continue
        dollar_match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", text[index:])
        if not quote and dollar_match:
            dollar_quote = dollar_match.group(0)
            index += len(dollar_quote)
            continue
        char = text[index]
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unbalanced parenthesized SQL fragment")


def _column_definition(item: str, name: str) -> str:
    rest = item[item.find(name) + len(name) :].strip()
    rest = re.split(
        r"\bDEFAULT\b|\bCONSTRAINT\b|\bCHECK\b|\bREFERENCES\b|\bGENERATED\b",
        rest,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    not_null = bool(re.search(r"\bNOT\s+NULL\b|\bPRIMARY\s+KEY\b", item, re.IGNORECASE))
    rest = re.sub(r"\bPRIMARY\s+KEY\b|\bNOT\s+NULL\b", "", rest, flags=re.IGNORECASE).strip()
    return _normalize_type(f"{rest} NOT NULL" if not_null else rest)


def _ensure_table(expected: ExpectedSchema, schema: str, table: str, *, defined: bool) -> TableExpectation:
    key = _qualified(schema, table)
    if key not in expected.tables:
        expected.tables[key] = TableExpectation(schema=schema, name=table, defined=defined)
    elif defined:
        expected.tables[key].defined = True
    return expected.tables[key]


def _extract_create_table(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>{_QUALIFIED})\s*\(",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return
    open_index = compact.find("(", match.end() - 1)
    close_index = _find_matching_paren(compact, open_index)
    schema, table_name = _parse_name(match.group("table"))
    table = _ensure_table(expected, schema, table_name, defined=True)
    for ordinal, item in enumerate(_split_csv(compact[open_index + 1 : close_index]), start=1):
        first_match = re.match(rf"\s*(?P<first>{_IDENT})", item)
        if not first_match:
            continue
        first = first_match.group("first")
        if first.upper() in {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"}:
            constraint = re.search(rf"\bCONSTRAINT\s+(?P<name>{_IDENT})", item, re.IGNORECASE)
            if constraint:
                table.constraints[_unquote(constraint.group("name"))] = ConstraintExpectation(
                    name=_unquote(constraint.group("name")),
                    expression=_extract_check_expression(item),
                )
            continue
        name = _unquote(first)
        table.columns.append(
            ColumnExpectation(
                name=name,
                definition=_column_definition(item, first),
                ordinal=ordinal,
            )
        )


def _extract_check_expression(item: str) -> str:
    match = re.search(r"\bCHECK\s*\(", item, re.IGNORECASE)
    if not match:
        return ""
    open_index = item.find("(", match.end() - 1)
    close_index = _find_matching_paren(item, open_index)
    return _normalize_expr(item[open_index + 1 : close_index])


def _extract_alter_table(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    table_match = re.match(
        rf"ALTER\s+TABLE\s+(?P<table>{_QUALIFIED})\s+(?P<rest>.*)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return
    schema, table_name = _parse_name(table_match.group("table"))
    table_key = _qualified(schema, table_name)
    rest = table_match.group("rest")
    table = _ensure_table(expected, schema, table_name, defined=False)
    if re.search(r"\bENABLE\s+ROW\s+LEVEL\s+SECURITY\b", rest, re.IGNORECASE):
        expected.rls_enabled.add(table_key)
    if re.search(r"\bFORCE\s+ROW\s+LEVEL\s+SECURITY\b", rest, re.IGNORECASE):
        expected.rls_forced.add(table_key)
    column = re.search(
        rf"\bADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<column>{_IDENT})(?P<definition>.*)",
        rest,
        re.IGNORECASE,
    )
    if column:
        name = _unquote(column.group("column"))
        if name not in table.columns_by_name:
            table.columns.append(
                ColumnExpectation(
                    name=name,
                    definition=_column_definition(rest, column.group("column")),
                    ordinal=len(table.columns) + 1,
                )
            )
    constraint = re.search(
        rf"\bADD\s+CONSTRAINT\s+(?P<constraint>{_IDENT})(?P<body>.*)",
        rest,
        re.IGNORECASE,
    )
    if constraint:
        name = _unquote(constraint.group("constraint"))
        table.constraints[name] = ConstraintExpectation(
            name=name,
            expression=_extract_check_expression(constraint.group("body")),
        )


def _extract_index(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        rf"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{_IDENT})\s+ON\s+(?P<table>{_QUALIFIED})(?:\s+USING\s+\w+)?\s*\(",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return
    open_index = compact.find("(", match.end() - 1)
    close_index = _find_matching_paren(compact, open_index)
    table_schema, table_name = _parse_name(match.group("table"))
    where = re.search(r"\bWHERE\s+(?P<predicate>.+)$", compact[close_index + 1 :], re.IGNORECASE)
    index_schema = table_schema
    name = _unquote(match.group("name"))
    expected.indexes[_qualified(index_schema, name)] = IndexExpectation(
        schema=index_schema,
        name=name,
        table=_qualified(table_schema, table_name),
        unique=bool(match.group("unique")),
        columns=tuple(_normalize_expr(part) for part in _split_csv(compact[open_index + 1 : close_index])),
        predicate=_normalize_expr(where.group("predicate")) if where else "",
    )


def _balanced_clause_after(keyword: str, compact: str, *, normalize: bool = True) -> str:
    match = re.search(rf"\b{keyword}\s*\(", compact, re.IGNORECASE)
    if not match:
        return ""
    open_index = compact.find("(", match.end() - 1)
    close_index = _find_matching_paren(compact, open_index)
    clause = " ".join(compact[open_index + 1 : close_index].strip().split())
    return _normalize_expr(clause) if normalize else clause


def _extract_policy(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        rf"CREATE\s+POLICY\s+(?P<policy>{_IDENT})\s+ON\s+(?P<table>{_QUALIFIED})",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return
    schema, table_name = _parse_name(match.group("table"))
    table_key = _qualified(schema, table_name)
    policy = _unquote(match.group("policy"))
    expected.policies.setdefault(table_key, {})[policy] = PolicyExpectation(
        name=policy,
        using=_balanced_clause_after("USING", compact, normalize=False),
        with_check=_balanced_clause_after("WITH\\s+CHECK", compact),
    )


def _parse_signature(compact: str, keyword: str) -> tuple[str, str, str] | None:
    match = re.search(rf"{keyword}\s+(?P<name>{_QUALIFIED})\s*\(", compact, re.IGNORECASE)
    if not match:
        return None
    open_index = compact.find("(", match.end() - 1)
    close_index = _find_matching_paren(compact, open_index)
    schema, name = _parse_name(match.group("name"))
    return schema, name, compact[open_index + 1 : close_index].strip()


def _function_key(schema: str, name: str, args: str) -> str:
    return f"{schema}.{name}({args})"


def _argument_types(args: str) -> tuple[str, ...]:
    types: list[str] = []
    for arg in _split_csv(args):
        parts = arg.strip().split()
        if not parts:
            continue
        if len(parts) == 1:
            types.append(parts[0].lower())
        else:
            types.append(" ".join(parts[1:]).lower())
    return tuple(types)


def _resolve_function_key(expected: ExpectedSchema, schema: str, name: str, args: str) -> str:
    key = _function_key(schema, name, args)
    if key in expected.functions:
        return key
    arg_types = _argument_types(args)
    for candidate_key, candidate in expected.functions.items():
        if (
            candidate.schema == schema
            and candidate.name == name
            and _argument_types(candidate.identity_arguments) == arg_types
        ):
            return candidate_key
    return key


def _extract_function(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    create_signature = _parse_signature(
        compact,
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION",
    )
    if create_signature:
        schema, name, args = create_signature
        search_path = ()
        search_path_match = re.search(
            r"\bSET\s+search_path\s*=\s*(?P<path>.*?)(?=\s+(?:AS|LANGUAGE|VOLATILE|STABLE|IMMUTABLE|SECURITY)\b)",
            compact,
            re.IGNORECASE,
        )
        if search_path_match:
            search_path = tuple(
                token.strip() for token in search_path_match.group("path").split(",")
            )
        expectation = FunctionExpectation(
            schema=schema,
            name=name,
            identity_arguments=args,
            security_definer=bool(re.search(r"\bSECURITY\s+DEFINER\b", compact, re.IGNORECASE)),
            search_path=search_path,
        )
        expected.functions[expectation.key] = expectation
        return

    owner_signature = _parse_signature(compact, r"ALTER\s+FUNCTION")
    if owner_signature and (owner := re.search(r"\bOWNER\s+TO\s+(?P<owner>\w+)", compact, re.IGNORECASE)):
        schema, name, args = owner_signature
        key = _resolve_function_key(expected, schema, name, args)
        current = expected.functions.get(key, FunctionExpectation(schema, name, args))
        expected.functions[key] = FunctionExpectation(
            schema=current.schema,
            name=current.name,
            identity_arguments=current.identity_arguments,
            owner=_unquote(owner.group("owner")),
            security_definer=current.security_definer,
            search_path=current.search_path,
            grants=set(current.grants),
            revokes=set(current.revokes),
        )
        return

    privilege = re.search(r"(?P<kind>GRANT|REVOKE)\s+(?:ALL|EXECUTE)\s+ON\s+FUNCTION", compact, re.IGNORECASE)
    privilege_signature = _parse_signature(compact, r"(?:GRANT|REVOKE)\s+(?:ALL|EXECUTE)\s+ON\s+FUNCTION")
    if privilege and privilege_signature:
        schema, name, args = privilege_signature
        roles_match = re.search(r"\s(?:TO|FROM)\s+(?P<roles>.+)$", compact, re.IGNORECASE)
        roles = {
            _unquote(role.strip()) for role in (roles_match.group("roles") if roles_match else "").rstrip(";").split(",")
            if role.strip()
        }
        key = _resolve_function_key(expected, schema, name, args)
        current = expected.functions.get(key, FunctionExpectation(schema, name, args))
        grants = set(current.grants)
        revokes = set(current.revokes)
        if privilege.group("kind").upper() == "GRANT":
            grants.update(roles)
        else:
            revokes.update(roles)
        expected.functions[key] = FunctionExpectation(
            schema=current.schema,
            name=current.name,
            identity_arguments=current.identity_arguments,
            owner=current.owner,
            security_definer=current.security_definer,
            search_path=current.search_path,
            grants=grants,
            revokes=revokes,
        )


def _extract_revoke(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    revoke = re.search(
        rf"REVOKE\s+ALL\s+ON\s+(?P<table>{_QUALIFIED})\s+FROM\s+(?P<roles>.+)",
        compact,
        re.IGNORECASE,
    )
    if not revoke or " ON FUNCTION " in compact.upper():
        return
    schema, table = _parse_name(revoke.group("table"))
    key = _qualified(schema, table)
    expected.table_revokes.setdefault(key, set()).update(
        _unquote(role.strip()) for role in revoke.group("roles").rstrip(";").split(",")
    )


def _extract_cron(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    for job, schedule in re.findall(
        r"cron\.schedule\s*\(\s*'([^']+)'\s*,\s*'([^']+)'",
        compact,
        flags=re.IGNORECASE,
    ):
        expected.cron_jobs[job] = schedule


def extract_expected_schema(schema_sql: str) -> ExpectedSchema:
    expected = ExpectedSchema()
    for raw_statement in sqlparse.split(schema_sql):
        statement = raw_statement.strip()
        if not statement:
            continue
        parsed = sqlparse.parse(statement)
        if not parsed:
            continue
        first = parsed[0].get_type()
        compact = _compact(statement)
        if first.startswith("CREATE"):
            _extract_create_table(statement, expected)
            _extract_index(statement, expected)
            _extract_policy(statement, expected)
            _extract_function(statement, expected)
        elif first == "ALTER":
            _extract_alter_table(statement, expected)
            _extract_function(statement, expected)
        elif compact.upper().startswith("REVOKE "):
            _extract_function(statement, expected)
            _extract_revoke(statement, expected)
        elif compact.upper().startswith("GRANT "):
            _extract_function(statement, expected)
        if "cron.schedule" in compact.lower():
            _extract_cron(statement, expected)

    for table in expected.tables.values():
        if not table.defined and table.columns:
            expected.warnings.append(
                f"{table.key} has ALTER-added columns but no parsed CREATE TABLE statement"
            )
    return expected


def _project_ref_from_url(supabase_url: str) -> str:
    host = urlparse(supabase_url).hostname
    if not host or not host.endswith(".supabase.co"):
        raise ValueError(
            "VIBECHECK_SUPABASE_URL must use the canonical https://<project-ref>.supabase.co host"
        )
    project_ref = host.removesuffix(".supabase.co")
    if not project_ref or "." in project_ref:
        raise ValueError(f"cannot derive Supabase project ref from {supabase_url!r}")
    return project_ref


async def _connect(timeout: float) -> asyncpg.Connection:
    supabase_url = os.environ.get("VIBECHECK_SUPABASE_URL", "")
    password = os.environ.get("VIBECHECK_SUPABASE_DB_PASSWORD", "")
    host = os.environ.get("VIBECHECK_DATABASE_HOST", "")
    if not supabase_url or not password or not host:
        raise RuntimeError(
            "VIBECHECK_SUPABASE_URL, VIBECHECK_SUPABASE_DB_PASSWORD, and "
            "VIBECHECK_DATABASE_HOST must be set"
        )
    return await asyncpg.connect(
        host=host,
        port=int(os.environ.get("VIBECHECK_DATABASE_PORT", str(DEFAULT_POOLER_PORT))),
        user=f"postgres.{_project_ref_from_url(supabase_url)}",
        password=password,
        database="postgres",
        ssl="require",
        statement_cache_size=0,
        timeout=int(timeout),
    )


def _mark(report: list[str], category: str, name: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "DRIFT"
    suffix = f" - {detail}" if detail else ""
    report.append(f"- `{category}` `{name}`: **{status}**{suffix}")
    return ok


def _row_key(row: Mapping[str, Any], name_key: str = "table_name") -> str:
    return _qualified(str(row["schema_name"]), str(row[name_key]))


async def _audit_tables(conn: Any, expected: ExpectedSchema, report: list[str]) -> tuple[bool, set[str]]:
    rows = await conn.fetch(
        """
        /* AUDIT_TABLES */
        SELECT n.nspname AS schema_name, c.relname AS table_name, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'v', 'm')
        """
    )
    actual = {_row_key(row): row for row in rows}
    columns = await conn.fetch(
        """
        /* AUDIT_COLUMNS */
        SELECT
            n.nspname AS schema_name,
            c.relname AS table_name,
            a.attname AS column_name,
            a.attnum AS ordinal_position,
            upper(format_type(a.atttypid, a.atttypmod)) ||
                CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END AS definition
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE a.attnum > 0 AND NOT a.attisdropped
        ORDER BY n.nspname, c.relname, a.attnum
        """
    )
    actual_columns: dict[str, list[Mapping[str, Any]]] = {}
    for row in columns:
        actual_columns.setdefault(_row_key(row), []).append(row)

    clean = True
    existing_tables: set[str] = set()
    report.extend(["## Tables And Columns", ""])
    for key, table in sorted(expected.tables.items()):
        row = actual.get(key)
        table_ok = row is not None and row["relkind"] == "r"
        clean &= _mark(report, "table", key, table_ok)
        if not table_ok:
            continue
        existing_tables.add(key)
        actual_by_name = {
            str(row["column_name"]): row
            for row in sorted(actual_columns.get(key, []), key=lambda item: int(item["ordinal_position"]))
        }
        actual_order = list(actual_by_name)
        expected_order = [column.name for column in table.columns]
        if expected_order:
            clean &= _mark(report, "column order", key, actual_order[: len(expected_order)] == expected_order)
        for column in table.columns:
            actual_column = actual_by_name.get(column.name)
            column_ok = (
                actual_column is not None
                and _normalize_type(str(actual_column["definition"])) == column.definition
            )
            detail = f"expected {column.definition}" if not column_ok else ""
            clean &= _mark(report, "column", f"{key}.{column.name}", column_ok, detail)
    return clean, existing_tables


async def _audit_indexes(conn: Any, expected: ExpectedSchema, report: list[str]) -> bool:
    rows = await conn.fetch(
        """
        /* AUDIT_INDEXES */
        SELECT schemaname AS schema_name, indexname AS index_name, tablename AS table_name, indexdef
        FROM pg_indexes
        """
    )
    actual = {_row_key(row, "index_name"): row for row in rows}
    clean = True
    report.extend(["", "## Indexes", ""])
    for key, expectation in sorted(expected.indexes.items()):
        row = actual.get(key)
        ok = False
        if row is not None:
            parsed = _parse_indexdef(str(row["indexdef"]))
            ok = (
                _qualified(str(row["schema_name"]), str(row["table_name"])) == expectation.table
                and parsed.unique == expectation.unique
                and parsed.columns == expectation.columns
                and _normalize_expr(parsed.predicate) == _normalize_expr(expectation.predicate)
            )
        clean &= _mark(report, "index", key, ok)
    return clean


def _parse_indexdef(indexdef: str) -> IndexExpectation:
    compact = _compact(indexdef)
    match = re.search(
        rf"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<name>{_IDENT})\s+ON\s+(?P<table>{_QUALIFIED})(?:\s+USING\s+\w+)?\s*\(",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return IndexExpectation("public", "", "public.", False, ())
    open_index = compact.find("(", match.end() - 1)
    close_index = _find_matching_paren(compact, open_index)
    schema, table = _parse_name(match.group("table"))
    where = re.search(r"\bWHERE\s+(?P<predicate>.+)$", compact[close_index + 1 :], re.IGNORECASE)
    return IndexExpectation(
        schema=schema,
        name=_unquote(match.group("name")),
        table=_qualified(schema, table),
        unique=bool(match.group("unique")),
        columns=tuple(_normalize_expr(part) for part in _split_csv(compact[open_index + 1 : close_index])),
        predicate=_normalize_expr(where.group("predicate")) if where else "",
    )


async def _audit_constraints(conn: Any, expected: ExpectedSchema, report: list[str], existing_tables: set[str]) -> bool:
    rows = await conn.fetch(
        """
        /* AUDIT_CONSTRAINTS */
        SELECT
            n.nspname AS schema_name,
            rel.relname AS table_name,
            c.conname AS constraint_name,
            pg_get_constraintdef(c.oid, true) AS definition
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        """
    )
    actual = {f"{_row_key(row)}.{row['constraint_name']}": row for row in rows}
    clean = True
    report.extend(["", "## Constraints", ""])
    for table_key, table in sorted(expected.tables.items()):
        if table_key not in existing_tables:
            continue
        for name, expectation in sorted(table.constraints.items()):
            key = f"{table_key}.{name}"
            row = actual.get(key)
            ok = False
            if row is not None and expectation.expression:
                actual_expr = _extract_check_expression(str(row["definition"]))
                ok = _normalize_expr(actual_expr) == expectation.expression
            elif row is not None:
                ok = True
            clean &= _mark(report, "constraint", key, ok)
    return clean


async def _audit_rls_privileges(
    conn: Any, expected: ExpectedSchema, report: list[str], existing_tables: set[str]
) -> bool:
    rls_rows = await conn.fetch(
        """
        /* AUDIT_RLS */
        SELECT n.nspname AS schema_name, c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        """
    )
    privileges = await conn.fetch(
        """
        /* AUDIT_TABLE_PRIVILEGES */
        SELECT table_schema AS schema_name, table_name, grantee, privilege_type
        FROM information_schema.table_privileges
        """
    )
    rls = {_row_key(row): row for row in rls_rows}
    privilege_map: dict[tuple[str, str], set[str]] = {}
    for row in privileges:
        privilege_map.setdefault((_row_key(row), str(row["grantee"])), set()).add(str(row["privilege_type"]))

    clean = True
    report.extend(["", "## RLS And Privileges", ""])
    for table in sorted(expected.rls_enabled & existing_tables):
        clean &= _mark(report, "rls enabled", table, bool(rls.get(table, {}).get("relrowsecurity")))
    for table in sorted(expected.rls_forced & existing_tables):
        clean &= _mark(report, "rls forced", table, bool(rls.get(table, {}).get("relforcerowsecurity")))
    for table, roles in sorted(expected.table_revokes.items()):
        if table not in existing_tables:
            continue
        for role in sorted(roles):
            clean &= _mark(
                report,
                "table revoke",
                f"{table} from {role}",
                not privilege_map.get((table, role)),
            )
    return clean


async def _audit_policies(conn: Any, expected: ExpectedSchema, report: list[str], existing_tables: set[str]) -> bool:
    rows = await conn.fetch(
        """
        /* AUDIT_POLICIES */
        SELECT schemaname AS schema_name, tablename AS table_name, policyname AS policy_name,
               qual AS using_expr, with_check AS with_check_expr
        FROM pg_policies
        """
    )
    actual = {f"{_row_key(row)}.{row['policy_name']}": row for row in rows}
    clean = True
    report.extend(["", "## Policies", ""])
    for table, policies in sorted(expected.policies.items()):
        if table not in existing_tables:
            continue
        for name, expectation in sorted(policies.items()):
            key = f"{table}.{name}"
            row = actual.get(key)
            ok = False
            if row is not None:
                ok = (
                    _normalize_expr(str(row.get("using_expr") or "")) == expectation.using
                    and _normalize_expr(str(row.get("with_check_expr") or "")) == expectation.with_check
                )
            clean &= _mark(report, "policy", key, ok)
    return clean


async def _audit_cron(conn: Any, expected: ExpectedSchema, report: list[str]) -> bool:
    report.extend(["", "## Cron", ""])
    try:
        rows = await conn.fetch("/* AUDIT_CRON */ SELECT jobname, schedule FROM cron.job")
    except asyncpg.PostgresError as exc:
        report.append(f"- `cron` `cron.job`: **WARN** - could not inspect cron.job: {exc.__class__.__name__}")
        return True
    cron = {str(row["jobname"]): str(row["schedule"]) for row in rows}
    clean = True
    for name, schedule in sorted(expected.cron_jobs.items()):
        clean &= _mark(report, "cron", name, cron.get(name) == schedule, f"expected `{schedule}`")
    return clean


async def _audit_functions(conn: Any, expected: ExpectedSchema, report: list[str]) -> bool:
    rows = await conn.fetch(
        """
        /* AUDIT_FUNCTIONS */
        SELECT
            n.nspname AS schema_name,
            p.proname AS function_name,
            pg_get_function_identity_arguments(p.oid) AS identity_arguments,
            pg_get_userbyid(p.proowner) AS owner,
            p.prosecdef AS security_definer,
            p.proconfig,
            p.proacl
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        """
    )
    actual = {
        _function_key(str(row["schema_name"]), str(row["function_name"]), str(row["identity_arguments"])): row
        for row in rows
    }
    clean = True
    report.extend(["", "## Functions", ""])
    for key, expectation in sorted(expected.functions.items()):
        row = actual.get(key)
        ok = row is not None
        if row is not None:
            execute_grantees = _execute_grantees(row.get("proacl") or [])
            ok = (
                (not expectation.owner or row["owner"] == expectation.owner)
                and bool(row["security_definer"]) == expectation.security_definer
                and _search_path(row.get("proconfig") or []) == expectation.search_path
                and expectation.grants.issubset(execute_grantees)
                and execute_grantees.isdisjoint(expectation.revokes)
            )
        clean &= _mark(report, "function", key, ok)
    return clean


def _execute_grantees(acl_items: Sequence[str]) -> set[str]:
    grantees: set[str] = set()
    for item in acl_items:
        grant_part = item.split("/", 1)[0]
        grantee, _, privileges = grant_part.partition("=")
        if "X" in privileges:
            grantees.add(grantee or "PUBLIC")
    return grantees


def _search_path(proconfig: Sequence[str]) -> tuple[str, ...]:
    for item in proconfig:
        key, _, value = item.partition("=")
        if key == "search_path":
            return tuple(part.strip() for part in value.split(","))
    return ()


async def _audit(conn: Any, expected: ExpectedSchema) -> tuple[bool, str]:
    if not (
        expected.tables
        or expected.indexes
        or expected.rls_enabled
        or expected.rls_forced
        or expected.policies
        or expected.cron_jobs
        or expected.functions
        or expected.table_revokes
    ):
        raise ValueError("schema parser found no auditable statements; refusing empty audit")
    report = ["# Vibecheck Schema Drift Audit", ""]
    for warning in expected.warnings:
        report.append(f"- `parser` `warning`: **WARN** - {warning}")
    clean_tables, existing_tables = await _audit_tables(conn, expected, report)
    checks = [
        clean_tables,
        await _audit_indexes(conn, expected, report),
        await _audit_constraints(conn, expected, report, existing_tables),
        await _audit_rls_privileges(conn, expected, report, existing_tables),
        await _audit_policies(conn, expected, report, existing_tables),
        await _audit_cron(conn, expected, report),
        await _audit_functions(conn, expected, report),
    ]
    return all(checks), "\n".join(report) + "\n"


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit vibecheck schema.sql against prod catalogs.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--json", action="store_true", help="emit a compact JSON summary")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(list(argv))


async def _main(argv: Iterable[str]) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    try:
        expected = extract_expected_schema(args.schema.read_text(encoding="utf-8"))
        conn = await _connect(args.timeout)
        try:
            clean, report = await _audit(conn, expected)
        finally:
            await conn.close()
    except Exception:
        logger.exception("schema audit failed")
        return 2
    if args.json:
        print(json.dumps({"clean": clean, "drift": not clean, "report": report}, sort_keys=True))
    else:
        print(report, end="")
    if args.report_path:
        args.report_path.write_text(report, encoding="utf-8")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
