#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import sqlparse

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "cache" / "schema.sql"
DEFAULT_POOLER_HOST = "aws-1-us-east-1.pooler.supabase.com"
DEFAULT_POOLER_PORT = 6543


@dataclass(frozen=True)
class IndexExpectation:
    table: str
    unique: bool
    definition: str
    predicate: str = ""


@dataclass(frozen=True)
class FunctionExpectation:
    owner: str = ""
    security_definer: bool = False
    search_path: str = ""
    grants: set[str] = field(default_factory=set)
    revokes: set[str] = field(default_factory=set)


@dataclass
class ExpectedSchema:
    tables: set[str] = field(default_factory=set)
    columns: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    indexes: dict[str, IndexExpectation] = field(default_factory=dict)
    constraints: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    rls_enabled: set[str] = field(default_factory=set)
    rls_forced: set[str] = field(default_factory=set)
    policies: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    policy_clauses: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    cron_jobs: dict[str, str] = field(default_factory=dict)
    functions: dict[str, FunctionExpectation] = field(default_factory=dict)
    table_revokes: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def _compact(sql: str) -> str:
    return " ".join(sqlparse.format(sql, strip_comments=True).split())


def _unquote(identifier: str) -> str:
    value = identifier.strip().rstrip(";")
    if "." in value:
        value = value.split(".")[-1]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('""', '"')
    return value


def _split_csv(text: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
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
    tail = "".join(current).strip()
    if tail:
        values.append(tail)
    return values


def _extract_create_table(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s*\((?P<body>.*)\)\s*;?$",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return
    table = _unquote(match.group("table"))
    expected.tables.add(table)
    for item in _split_csv(match.group("body")):
        first_match = re.match(r"\s*(\"[^\"]+\"|\w+)", item)
        if not first_match:
            continue
        first = first_match.group(1)
        if first.upper() in {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"}:
            constraint = re.search(r"\bCONSTRAINT\s+(\"[^\"]+\"|\w+)", item, re.IGNORECASE)
            if constraint:
                expected.constraints[table].add(_unquote(constraint.group(1)))
            continue
        expected.columns[table].add(_unquote(first))


def _extract_alter_table(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    table_match = re.match(
        r"ALTER\s+TABLE\s+(?P<table>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s+(?P<rest>.*)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return
    table = _unquote(table_match.group("table"))
    rest = table_match.group("rest")
    if re.search(r"\bENABLE\s+ROW\s+LEVEL\s+SECURITY\b", rest, re.IGNORECASE):
        expected.rls_enabled.add(table)
    if re.search(r"\bFORCE\s+ROW\s+LEVEL\s+SECURITY\b", rest, re.IGNORECASE):
        expected.rls_forced.add(table)
    column = re.search(
        r"\bADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<column>\"[^\"]+\"|\w+)",
        rest,
        re.IGNORECASE,
    )
    if column:
        expected.columns[table].add(_unquote(column.group("column")))
    constraint = re.search(
        r"\bADD\s+CONSTRAINT\s+(?P<constraint>\"[^\"]+\"|\w+)",
        rest,
        re.IGNORECASE,
    )
    if constraint:
        expected.constraints[table].add(_unquote(constraint.group("constraint")))


def _extract_index(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        r"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\"[^\"]+\"|\w+)\s+ON\s+(?P<table>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return
    name = _unquote(match.group("name"))
    where = re.search(r"\bWHERE\s+(?P<predicate>.+)$", compact, re.IGNORECASE)
    expected.indexes[name] = IndexExpectation(
        table=_unquote(match.group("table")),
        unique=bool(match.group("unique")),
        definition=compact,
        predicate=where.group("predicate") if where else "",
    )


def _extract_policy(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    match = re.search(
        r"CREATE\s+POLICY\s+(?P<policy>\"[^\"]+\"|\w+)\s+ON\s+(?P<table>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return
    table = _unquote(match.group("table"))
    policy = _unquote(match.group("policy"))
    expected.policies[table].add(policy)
    using = re.search(r"\bUSING\s*\((?P<using>.*?)\)\s*(?:WITH\s+CHECK|$)", compact, re.IGNORECASE)
    check = re.search(r"\bWITH\s+CHECK\s*\((?P<check>.*?)\)\s*$", compact, re.IGNORECASE)
    expected.policy_clauses[(table, policy)] = (
        using.group("using").strip() if using else "",
        check.group("check").strip() if check else "",
    )


def _extract_function(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    create_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?P<name>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s*\(",
        compact,
        re.IGNORECASE,
    )
    if create_match:
        name = _unquote(create_match.group("name"))
        search_path = ""
        search_path_match = re.search(r"\bSET\s+search_path\s*=\s*([^$]+?)\s+AS\s", compact, re.IGNORECASE)
        if search_path_match:
            search_path = search_path_match.group(1).strip()
        expected.functions[name] = FunctionExpectation(
            security_definer=bool(re.search(r"\bSECURITY\s+DEFINER\b", compact, re.IGNORECASE)),
            search_path=search_path,
        )
        return

    owner = re.search(
        r"ALTER\s+FUNCTION\s+(?P<name>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s*\([^)]*\)\s+OWNER\s+TO\s+(?P<owner>\"[^\"]+\"|\w+)",
        compact,
        re.IGNORECASE,
    )
    if owner:
        name = _unquote(owner.group("name"))
        current = expected.functions.get(name, FunctionExpectation())
        expected.functions[name] = FunctionExpectation(
            owner=_unquote(owner.group("owner")),
            security_definer=current.security_definer,
            search_path=current.search_path,
            grants=set(current.grants),
            revokes=set(current.revokes),
        )
        return

    privilege = re.search(
        r"(?P<kind>GRANT|REVOKE)\s+(?:ALL|EXECUTE)\s+ON\s+FUNCTION\s+(?P<name>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s*\([^)]*\)\s+(?:TO|FROM)\s+(?P<roles>.+)",
        compact,
        re.IGNORECASE,
    )
    if privilege:
        name = _unquote(privilege.group("name"))
        current = expected.functions.get(name, FunctionExpectation())
        grants = set(current.grants)
        revokes = set(current.revokes)
        roles = {_unquote(role.strip()) for role in privilege.group("roles").rstrip(";").split(",")}
        if privilege.group("kind").upper() == "GRANT":
            grants.update(roles)
        else:
            revokes.update(roles)
        expected.functions[name] = FunctionExpectation(
            owner=current.owner,
            security_definer=current.security_definer,
            search_path=current.search_path,
            grants=grants,
            revokes=revokes,
        )


def _extract_revoke(statement: str, expected: ExpectedSchema) -> None:
    compact = _compact(statement)
    revoke = re.search(
        r"REVOKE\s+ALL\s+ON\s+(?P<table>(?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)\s+FROM\s+(?P<roles>.+)",
        compact,
        re.IGNORECASE,
    )
    if not revoke or " ON FUNCTION " in compact.upper():
        return
    table = _unquote(revoke.group("table"))
    expected.table_revokes[table].update(
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
        elif first == "REVOKE" or compact.upper().startswith("REVOKE "):
            _extract_function(statement, expected)
            _extract_revoke(statement, expected)
        elif first == "GRANT" or compact.upper().startswith("GRANT "):
            _extract_function(statement, expected)
        elif first == "UNKNOWN" or "cron.schedule" in statement:
            _extract_cron(statement, expected)
    return expected


def _project_ref_from_url(supabase_url: str) -> str:
    host = urlparse(supabase_url).hostname
    if not host:
        raise ValueError(f"cannot derive Supabase project ref from {supabase_url!r}")
    return host.split(".", 1)[0]


async def _connect() -> asyncpg.Connection:
    supabase_url = os.environ.get("VIBECHECK_SUPABASE_URL", "")
    password = os.environ.get("VIBECHECK_SUPABASE_DB_PASSWORD", "")
    if not supabase_url or not password:
        raise RuntimeError(
            "VIBECHECK_SUPABASE_URL and VIBECHECK_SUPABASE_DB_PASSWORD must be set"
        )
    return await asyncpg.connect(
        host=os.environ.get("VIBECHECK_DATABASE_HOST", DEFAULT_POOLER_HOST),
        port=int(os.environ.get("VIBECHECK_DATABASE_PORT", str(DEFAULT_POOLER_PORT))),
        user=f"postgres.{_project_ref_from_url(supabase_url)}",
        password=password,
        database="postgres",
        ssl="require",
        statement_cache_size=0,
        timeout=10,
    )


def _mark(report: list[str], category: str, name: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "DRIFT"
    suffix = f" — {detail}" if detail else ""
    report.append(f"- `{category}` `{name}`: **{status}**{suffix}")
    return ok


async def _audit(  # noqa: PLR0912
    conn: asyncpg.Connection, expected: ExpectedSchema
) -> tuple[bool, str]:
    report = ["# Vibecheck Schema Drift Audit", ""]
    clean = True

    report.extend(["## Tables And Columns", ""])
    for table in sorted(expected.tables | set(expected.columns)):
        table_exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table}")
        clean &= _mark(report, "table", table, table_exists is not None)
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            """,
            table,
        )
        present_columns = {row["column_name"] for row in rows}
        for column in sorted(expected.columns.get(table, set())):
            clean &= _mark(report, "column", f"{table}.{column}", column in present_columns)

    report.extend(["", "## Indexes", ""])
    index_rows = await conn.fetch(
        "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname = 'public'"
    )
    indexes = {row["indexname"]: row for row in index_rows}
    for name, expectation in sorted(expected.indexes.items()):
        row = indexes.get(name)
        ok = False
        if row is not None and row["tablename"] == expectation.table:
            indexdef = row["indexdef"]
            ok = ("UNIQUE INDEX" in indexdef) == expectation.unique
            if expectation.predicate:
                ok = ok and "WHERE" in indexdef
        clean &= _mark(report, "index", name, ok)

    report.extend(["", "## Constraints", ""])
    constraint_rows = await conn.fetch(
        """
        SELECT c.conname, rel.relname AS table_name
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public'
        """
    )
    constraints = {(row["table_name"], row["conname"]) for row in constraint_rows}
    for table, names in sorted(expected.constraints.items()):
        for name in sorted(names):
            clean &= _mark(report, "constraint", f"{table}.{name}", (table, name) in constraints)

    report.extend(["", "## RLS And Privileges", ""])
    rls_rows = await conn.fetch(
        """
        SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        """
    )
    rls = {row["relname"]: row for row in rls_rows}
    for table in sorted(expected.rls_enabled):
        clean &= _mark(report, "rls enabled", table, bool(rls.get(table, {}).get("relrowsecurity")))
    for table in sorted(expected.rls_forced):
        clean &= _mark(report, "rls forced", table, bool(rls.get(table, {}).get("relforcerowsecurity")))

    report.extend(["", "## Policies", ""])
    policy_rows = await conn.fetch(
        """
        SELECT tablename, policyname, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'public'
        """
    )
    policies = {(row["tablename"], row["policyname"]): row for row in policy_rows}
    for table, names in sorted(expected.policies.items()):
        for name in sorted(names):
            clean &= _mark(report, "policy", f"{table}.{name}", (table, name) in policies)

    report.extend(["", "## Cron", ""])
    try:
        cron_rows = await conn.fetch("SELECT jobname, schedule FROM cron.job")
        cron = {row["jobname"]: row["schedule"] for row in cron_rows}
    except asyncpg.UndefinedTableError:
        cron = {}
    for name, schedule in sorted(expected.cron_jobs.items()):
        clean &= _mark(report, "cron", name, cron.get(name) == schedule, f"expected `{schedule}`")

    report.extend(["", "## Functions", ""])
    function_rows = await conn.fetch(
        """
        SELECT
            p.proname,
            pg_get_userbyid(p.proowner) AS owner,
            p.prosecdef,
            COALESCE(array_to_string(p.proconfig, ','), '') AS proconfig,
            COALESCE(array_to_string(p.proacl, ','), '') AS proacl
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
        """
    )
    functions = {row["proname"]: row for row in function_rows}
    for name, expectation in sorted(expected.functions.items()):
        row = functions.get(name)
        ok = row is not None
        if row is not None:
            if expectation.owner:
                ok = ok and row["owner"] == expectation.owner
            ok = ok and bool(row["prosecdef"]) == expectation.security_definer
            if expectation.search_path:
                ok = ok and f"search_path={expectation.search_path}" in row["proconfig"]
            proacl = row["proacl"]
            for role in expectation.grants:
                ok = ok and f"{role}=X" in proacl
            for role in expectation.revokes:
                ok = ok and f"{role}=X" not in proacl
        clean &= _mark(report, "function", name, ok)

    return clean, "\n".join(report) + "\n"


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit vibecheck schema.sql against prod catalogs.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args(list(argv))


async def _main(argv: Iterable[str]) -> int:
    args = _parse_args(argv)
    try:
        expected = extract_expected_schema(args.schema.read_text(encoding="utf-8"))
        conn = await _connect()
        try:
            clean, report = await _audit(conn, expected)
        finally:
            await conn.close()
    except Exception as exc:
        print(f"ERROR: schema audit failed: {exc}", file=sys.stderr)
        return 2
    print(report, end="")
    if args.report_path:
        args.report_path.write_text(report, encoding="utf-8")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
