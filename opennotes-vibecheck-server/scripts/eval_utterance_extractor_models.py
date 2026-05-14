"""TASK-1644 -- gemini-3.1-flash vs gemini-3.1-flash-lite utterance extraction bake-off.

Four subcommands, executed in order:

  corpus  -- build bucketed manifest from exported vibecheck_scrapes rows (free)
  run     -- run both models, capture metrics (burns Vertex)
  judge   -- Gemini Pro judges long+medium subset (burns Vertex)
  report  -- aggregate metrics + verdicts into REPORT.md (free)

Usage (from opennotes-vibecheck-server/):

    uv run python scripts/eval_utterance_extractor_models.py corpus \\
        --input ~/Downloads/vibecheck_scrapes_rows.json

    uv run python scripts/eval_utterance_extractor_models.py run \\
        --input ~/Downloads/vibecheck_scrapes_rows.json

    uv run python scripts/eval_utterance_extractor_models.py judge

    uv run python scripts/eval_utterance_extractor_models.py report
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import random
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel

from src.cache.scrape_cache import CachedScrape, SupabaseScrapeCache
from src.config import Settings
from src.firecrawl_client import ScrapeMetadata, ScrapeResult
from src.services.gemini_agent import build_agent, run_vertex_agent_with_retry
from src.services.vertex_limiter import vertex_slot
from src.utterances.extractor import (
    EXTRACTOR_SYSTEM_PROMPT,
    ExtractorDeps,
    _agent_user_prompt,
    _register_tools,
)
from src.utterances.schema import UtterancesPayload

if TYPE_CHECKING:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
EVAL_DIR = REPO_ROOT / "docs" / "specs" / "vibecheck" / "utterance-model-eval"
CORPUS_PATH = EVAL_DIR / "corpus.json"
RUNS_DIR = EVAL_DIR / "runs"
JUDGMENTS_DIR = EVAL_DIR / "judgments"
REPORT_PATH = EVAL_DIR / "REPORT.md"
JUDGE_PROMPT_PATH = EVAL_DIR / "_judge_prompt.txt"

SHORT_MAX = 5_000
MEDIUM_MAX = 25_000

MODEL_FLASH = "google-vertex:gemini-3-flash-preview"
MODEL_FLASH_LITE = "google-vertex:gemini-3-flash-lite-preview"

MODEL_KEYS: list[Literal["flash", "flash_lite"]] = ["flash", "flash_lite"]
MODEL_DISPLAY: dict[str, str] = {
    "flash": MODEL_FLASH,
    "flash_lite": MODEL_FLASH_LITE,
}


def _bucket(markdown_length: int) -> Literal["short", "medium", "long"]:
    if markdown_length < SHORT_MAX:
        return "short"
    if markdown_length <= MEDIUM_MAX:
        return "medium"
    return "long"


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_rows(input_path: Path) -> list[dict[str, Any]]:
    """Load exported scrape rows from JSON or CSV.

    Supabase Studio's row-display JSON export truncates long text columns at
    10243 chars; the SQL-snippet CSV export does not. Prefer CSV exports for
    long-text comparisons.
    """
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        return json.loads(input_path.read_text(encoding="utf-8"))
    if suffix == ".csv":
        csv.field_size_limit(sys.maxsize)
        with input_path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    raise SystemExit(f"Unsupported input extension {suffix!r}: expected .json or .csv")


def cmd_corpus(args: argparse.Namespace) -> None:
    """Phase 1: build bucketed manifest from exported rows."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    rows = _load_rows(input_path)
    print(f"Loaded {len(rows)} rows from {input_path}")

    entries: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        markdown = row.get("markdown") or ""
        if not markdown.strip():
            skipped += 1
            continue
        html = row.get("html") or ""
        ml = len(markdown)
        hl = len(html)
        entries.append(
            {
                "scrape_id": row["scrape_id"],
                "normalized_url": row["normalized_url"],
                "page_kind": row.get("page_kind"),
                "markdown_length": ml,
                "html_length": hl,
                "bucket": _bucket(ml),
            }
        )

    print(f"Skipped {skipped} rows with empty/null markdown")
    print(f"Corpus: {len(entries)} entries")

    by_bucket: dict[str, int] = {"short": 0, "medium": 0, "long": 0}
    for e in entries:
        by_bucket[e["bucket"]] += 1
    print(f"  short (<{SHORT_MAX}): {by_bucket['short']}")
    print(f"  medium ({SHORT_MAX}-{MEDIUM_MAX}): {by_bucket['medium']}")
    print(f"  long (>{MEDIUM_MAX}): {by_bucket['long']}")

    manifest: dict[str, Any] = {
        "_meta": {
            "bucket_thresholds": {
                "short_max": SHORT_MAX,
                "medium_max": MEDIUM_MAX,
                "description": (
                    f"short < {SHORT_MAX} chars; "
                    f"medium {SHORT_MAX}-{MEDIUM_MAX}; "
                    f"long > {MEDIUM_MAX}"
                ),
            },
            "total": len(entries),
            "by_bucket": by_bucket,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "entries": entries,
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {CORPUS_PATH}")


async def _run_single_model(
    row: dict[str, Any],
    model_key: Literal["flash", "flash_lite"],
    settings: Settings,
) -> dict[str, Any]:
    """Run one model against one scrape row. Returns a metrics dict."""
    metadata = ScrapeMetadata(
        title=row.get("page_title"),
        source_url=row.get("final_url") or row.get("url") or row.get("normalized_url"),
    )

    scrape = CachedScrape(
        markdown=row.get("markdown"),
        html=row.get("html"),
        raw_html=row.get("raw_html"),
        screenshot=None,
        links=None,
        metadata=metadata,
        warning=None,
        storage_key=None,
    )

    class _StubScrapeCache(SupabaseScrapeCache):
        """Hermetic stub -- no GCS, no Supabase. Screenshot always returns None."""

        def __init__(self) -> None:
            object.__init__(self)

        async def signed_screenshot_url(self, scrape: ScrapeResult) -> str | None:  # type: ignore[override]
            _ = scrape
            return None

    stub_cache = _StubScrapeCache()

    model_string = MODEL_DISPLAY[model_key]
    patched_settings = settings.model_copy(update={"VERTEXAI_FAST_MODEL": model_string})

    markdown = scrape.markdown or ""
    if not markdown.strip():
        return {
            "model": model_key,
            "error": "empty markdown",
            "latency_ms": 0,
            "request_tokens": 0,
            "response_tokens": 0,
            "utterance_count": 0,
            "char_coverage_ratio": 0.0,
            "dedup_rate": 0.0,
            "payload": None,
        }

    user_prompt = _agent_user_prompt(markdown, scrape)

    agent = build_agent(
        patched_settings,
        output_type=UtterancesPayload,
        system_prompt=EXTRACTOR_SYSTEM_PROMPT,
        name="vibecheck.utterance_extractor_eval",
    )
    _register_tools(agent)
    deps = ExtractorDeps(scrape=scrape, scrape_cache=stub_cache)  # type: ignore[arg-type]

    t0 = time.monotonic()
    error: str | None = None
    payload_dict: dict[str, Any] | None = None
    request_tokens = 0
    response_tokens = 0
    utterance_count = 0
    char_coverage_ratio = 0.0
    dedup_rate = 0.0

    try:
        async with vertex_slot(patched_settings):
            result = await run_vertex_agent_with_retry(agent, user_prompt, deps=deps)  # pyright: ignore[reportArgumentType]

        usage = result.usage()
        request_tokens = usage.request_tokens or 0
        response_tokens = usage.response_tokens or 0

        payload = cast(UtterancesPayload, cast(object, result.output))

        utterances = payload.utterances
        utterance_count = len(utterances)

        all_text = " ".join(u.text for u in utterances)
        if markdown:
            char_coverage_ratio = min(len(all_text) / len(markdown), 1.0)

        texts = [u.text for u in utterances]
        if texts:
            unique_texts = len(set(texts))
            dedup_rate = 1.0 - (unique_texts / len(texts))

        payload_dict = json.loads(payload.model_dump_json())

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    latency_ms = int((time.monotonic() - t0) * 1000)

    return {
        "model": model_key,
        "error": error,
        "latency_ms": latency_ms,
        "request_tokens": request_tokens,
        "response_tokens": response_tokens,
        "utterance_count": utterance_count,
        "char_coverage_ratio": char_coverage_ratio,
        "dedup_rate": dedup_rate,
        "payload": payload_dict,
    }


async def _run_scrape(
    row: dict[str, Any],
    out_path: Path,
    settings: Settings,
    force: bool,
) -> None:
    scrape_id = row["scrape_id"]

    if out_path.exists() and not force:
        print(f"  [{scrape_id}] skip (exists)")
        return

    print(f"  [{scrape_id}] running flash...")
    flash_result = await _run_single_model(row, "flash", settings)
    print(f"  [{scrape_id}] running flash_lite...")
    lite_result = await _run_single_model(row, "flash_lite", settings)

    output: dict[str, Any] = {
        "scrape_id": scrape_id,
        "normalized_url": row.get("normalized_url"),
        "markdown_length": len(row.get("markdown") or ""),
        "html_length": len(row.get("html") or ""),
        "bucket": _bucket(len(row.get("markdown") or "")),
        "flash": flash_result,
        "flash_lite": lite_result,
    }
    out_path.write_text(json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"  [{scrape_id}] wrote {out_path.name}")


def cmd_run(args: argparse.Namespace) -> None:
    """Phase 2: run both models against all corpus scrapes."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    if not CORPUS_PATH.exists():
        raise SystemExit(f"corpus.json not found at {CORPUS_PATH} -- run `corpus` first")

    rows_by_id: dict[str, dict[str, Any]] = {
        row["scrape_id"]: row for row in _load_rows(input_path)
    }

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = corpus["entries"]

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    settings = Settings()

    async def _run_all() -> None:
        for entry in entries:
            scrape_id = entry["scrape_id"]
            row = rows_by_id.get(scrape_id)
            if row is None:
                print(f"  [{scrape_id}] not found in input -- skip")
                continue
            out_path = RUNS_DIR / f"{scrape_id}.json"
            await _run_scrape(row, out_path, settings, force=bool(args.force))

    asyncio.run(_run_all())
    print(f"\nRuns complete. Outputs in: {RUNS_DIR}")


class JudgeVerdict(BaseModel):
    fidelity_winner: Literal["A", "B", "tie"]
    coverage_winner: Literal["A", "B", "tie"]
    granularity_winner: Literal["A", "B", "tie"]
    fidelity_rationale: str
    coverage_rationale: str
    granularity_rationale: str
    judge_model: str = ""
    judge_prompt_sha: str = ""


async def _judge_scrape(
    run_data: dict[str, Any],
    out_path: Path,
    settings: Settings,
    judge_prompt: str,
    judge_prompt_sha: str,
    force: bool,
) -> None:
    scrape_id = run_data["scrape_id"]

    if out_path.exists() and not force:
        print(f"  [{scrape_id}] skip (exists)")
        return

    flash_payload = run_data.get("flash", {}).get("payload")
    lite_payload = run_data.get("flash_lite", {}).get("payload")

    if flash_payload is None or lite_payload is None:
        print(f"  [{scrape_id}] skip -- missing payload (run errors?)")
        return

    flip = random.random() < 0.5
    if flip:
        system_a, system_b = "flash", "flash_lite"
        a_payload, b_payload = flash_payload, lite_payload
    else:
        system_a, system_b = "flash_lite", "flash"
        a_payload, b_payload = lite_payload, flash_payload

    source_markdown = run_data.get("_source_markdown_preview", "")

    user_prompt = (
        judge_prompt.replace("{source_markdown}", source_markdown[:4000])
        .replace("{system_a_json}", json.dumps(a_payload, indent=2)[:8000])
        .replace("{system_b_json}", json.dumps(b_payload, indent=2)[:8000])
    )

    model_name = settings.VERTEXAI_MODEL

    agent = build_agent(
        settings,
        output_type=JudgeVerdict,
        system_prompt=None,
        name="vibecheck.utterance_model_judge",
        tier="synthesis",
    )

    try:
        async with vertex_slot(settings):
            result = await run_vertex_agent_with_retry(agent, user_prompt)
        verdict = cast(JudgeVerdict, cast(object, result.output))
        verdict.judge_model = model_name
        verdict.judge_prompt_sha = judge_prompt_sha
        verdict_dict = json.loads(verdict.model_dump_json())
        verdict_dict["_blind_mapping"] = {"A": system_a, "B": system_b, "flip": flip}
        out_path.write_text(json.dumps(verdict_dict, indent=2) + "\n", encoding="utf-8")
        print(f"  [{scrape_id}] judged")
    except Exception as exc:
        print(f"  [{scrape_id}] judge error: {exc}")
        out_path.write_text(
            json.dumps({"_error": str(exc), "scrape_id": scrape_id}, indent=2) + "\n",
            encoding="utf-8",
        )


def _load_run_files() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    results = []
    for p in sorted(RUNS_DIR.glob("*.json")):
        try:
            results.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def cmd_judge(args: argparse.Namespace) -> None:
    """Phase 3: LLM-as-judge on long + medium sample."""
    runs = _load_run_files()
    if not runs:
        raise SystemExit(f"No run files found in {RUNS_DIR} -- run `run` first")

    judge_prompt = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    judge_prompt_sha = _sha256_hex(judge_prompt)[:12]

    to_judge = [r for r in runs if r.get("bucket") in {"long", "medium"}]
    print(f"Judging {len(to_judge)} entries (long + medium bucket)")

    JUDGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    settings = Settings()

    async def _judge_all() -> None:
        for run_data in to_judge:
            scrape_id = run_data["scrape_id"]
            out_path = JUDGMENTS_DIR / f"{scrape_id}.json"
            await _judge_scrape(
                run_data,
                out_path,
                settings,
                judge_prompt,
                judge_prompt_sha,
                force=bool(args.force),
            )

    asyncio.run(_judge_all())
    print(f"\nJudgments complete. Outputs in: {JUDGMENTS_DIR}")


def _safe_median(vals: list[float]) -> float | None:
    clean = [v for v in vals if v is not None]
    return statistics.median(clean) if clean else None


def _safe_mean(vals: list[float]) -> float | None:
    clean = [v for v in vals if v is not None]
    return sum(clean) / len(clean) if clean else None


def _p95(vals: list[float]) -> float | None:
    clean = sorted(v for v in vals if v is not None)
    if not clean:
        return None
    idx = int(len(clean) * 0.95)
    return clean[min(idx, len(clean) - 1)]


def _table_row(label: str, flash: Any, lite: Any) -> str:
    def fmt(v: Any) -> str:
        if v is None:
            return "--"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    return f"| {label} | {fmt(flash)} | {fmt(lite)} |"


def cmd_report(args: argparse.Namespace) -> None:
    """Phase 4: aggregate metrics and judgments into REPORT.md."""
    _ = args
    if not CORPUS_PATH.exists():
        raise SystemExit("corpus.json not found -- run `corpus` first")

    runs = _load_run_files()
    if not runs:
        raise SystemExit(f"No run files in {RUNS_DIR} -- run `run` first")

    judgments: list[dict[str, Any]] = []
    if JUDGMENTS_DIR.exists():
        for p in sorted(JUDGMENTS_DIR.glob("*.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
                if "_error" not in j:
                    judgments.append(j)
            except Exception:
                pass

    buckets: dict[str, list[dict[str, Any]]] = {"short": [], "medium": [], "long": []}
    for run in runs:
        bucket = run.get("bucket", "short")
        if bucket in buckets:
            buckets[bucket].append(run)

    def _bucket_table(bucket_runs: list[dict[str, Any]]) -> str:
        if not bucket_runs:
            return "_No data._\n"

        def _vals(model_key: str, field: str) -> list[float]:
            out: list[float] = []
            for r in bucket_runs:
                m = r.get(model_key, {})
                if m.get("error") is None:
                    v = m.get(field)
                    if v is not None:
                        out.append(float(v))
            return out

        def _error_rate(model_key: str) -> float:
            errs = sum(1 for r in bucket_runs if r.get(model_key, {}).get("error") is not None)
            return errs / len(bucket_runs) if bucket_runs else 0.0

        rows = [
            "| Metric | flash | flash_lite |",
            "|--------|-------|-----------|",
            _table_row(
                "median latency ms",
                _safe_median(_vals("flash", "latency_ms")),
                _safe_median(_vals("flash_lite", "latency_ms")),
            ),
            _table_row(
                "p95 latency ms",
                _p95(_vals("flash", "latency_ms")),
                _p95(_vals("flash_lite", "latency_ms")),
            ),
            _table_row(
                "median request tokens",
                _safe_median(_vals("flash", "request_tokens")),
                _safe_median(_vals("flash_lite", "request_tokens")),
            ),
            _table_row(
                "median response tokens",
                _safe_median(_vals("flash", "response_tokens")),
                _safe_median(_vals("flash_lite", "response_tokens")),
            ),
            _table_row(
                "mean utterance count",
                _safe_mean(_vals("flash", "utterance_count")),
                _safe_mean(_vals("flash_lite", "utterance_count")),
            ),
            _table_row(
                "mean char coverage ratio",
                _safe_mean(_vals("flash", "char_coverage_ratio")),
                _safe_mean(_vals("flash_lite", "char_coverage_ratio")),
            ),
            _table_row(
                "mean dedup rate",
                _safe_mean(_vals("flash", "dedup_rate")),
                _safe_mean(_vals("flash_lite", "dedup_rate")),
            ),
            _table_row("error rate", _error_rate("flash"), _error_rate("flash_lite")),
        ]
        return "\n".join(rows) + "\n"

    def _judge_win_rates() -> str:
        if not judgments:
            return "_No judgments available._\n"

        def _unblind(verdict: dict[str, Any], raw_winner: str) -> str:
            mapping = verdict.get("_blind_mapping", {})
            if raw_winner == "tie":
                return "tie"
            return str(mapping.get(raw_winner, raw_winner))

        dims: dict[str, dict[str, int]] = {
            "fidelity": {"flash": 0, "flash_lite": 0, "tie": 0},
            "coverage": {"flash": 0, "flash_lite": 0, "tie": 0},
            "granularity": {"flash": 0, "flash_lite": 0, "tie": 0},
        }
        for j in judgments:
            for dim in ("fidelity", "coverage", "granularity"):
                raw = j.get(f"{dim}_winner", "tie")
                winner = _unblind(j, raw)
                if winner in dims[dim]:
                    dims[dim][winner] += 1

        n = len(judgments)
        rows = [
            "| Dimension | flash wins | flash_lite wins | tie |",
            "|-----------|-----------|----------------|-----|",
        ]
        for dim, counts in dims.items():
            rows.append(
                f"| {dim} "
                f"| {counts['flash']}/{n} "
                f"| {counts['flash_lite']}/{n} "
                f"| {counts['tie']}/{n} |"
            )
        return "\n".join(rows) + "\n"

    parts: list[str] = [
        "# Utterance Extractor Model Bake-off -- Report\n",
        f"_Generated: {datetime.now(UTC).isoformat()}_\n",
        f"_Models: `{MODEL_FLASH}` (flash) vs `{MODEL_FLASH_LITE}` (flash_lite)_\n",
        f"_Corpus: {len(runs)} scrapes_\n\n",
    ]

    for bucket_name in ("short", "medium", "long"):
        bdata = buckets[bucket_name]
        threshold_note = {
            "short": f"markdown < {SHORT_MAX} chars",
            "medium": f"markdown {SHORT_MAX}-{MEDIUM_MAX} chars",
            "long": f"markdown > {MEDIUM_MAX} chars",
        }[bucket_name]
        parts.append(f"## Bucket: {bucket_name} ({threshold_note})\n\n")
        parts.append(f"_n = {len(bdata)}_\n\n")
        parts.append(_bucket_table(bdata))
        parts.append("\n")

    parts.append("## Judge Win Rates (long + medium subset)\n\n")
    parts.append(f"_n judgments = {len(judgments)}_\n\n")
    parts.append(_judge_win_rates())
    parts.append("\n")

    parts.append("## Per-bucket Recommendations\n\n")
    parts.append(
        "> Operator: fill in this section after reviewing the tables above.\n"
        "> Suggested template per bucket:\n"
        "> **Recommendation:** use `flash` / `flash_lite` / either\n"
        "> **Reasoning:** latency delta is X ms (Y%), quality delta is Z utterances"
        " on average,\n"
        "> judge favoured A on fidelity N/M times.\n\n"
    )
    for bucket_name in ("short", "medium", "long"):
        parts.append(f"### {bucket_name}\n\n_TBD_\n\n")

    REPORT_PATH.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval_utterance_extractor_models",
        description=(
            "Benchmark gemini-3.1-flash vs gemini-3.1-flash-lite for utterance extraction."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_corpus = sub.add_parser("corpus", help="Build bucketed manifest from exported rows (free)")
    p_corpus.add_argument(
        "--input",
        default="~/Downloads/vibecheck_scrapes_rows.json",
        help="Path to the exported vibecheck_scrapes JSON rows (default: %(default)s)",
    )
    p_corpus.set_defaults(func=cmd_corpus)

    p_run = sub.add_parser("run", help="Run both models against corpus scrapes (burns Vertex)")
    p_run.add_argument(
        "--input",
        default="~/Downloads/vibecheck_scrapes_rows.json",
        help="Path to the exported vibecheck_scrapes JSON rows (default: %(default)s)",
    )
    p_run.add_argument(
        "--force",
        action="store_true",
        help="Re-run even when output file already exists",
    )
    p_run.set_defaults(func=cmd_run)

    p_judge = sub.add_parser("judge", help="Gemini Pro judges long+medium subset (burns Vertex)")
    p_judge.add_argument(
        "--force",
        action="store_true",
        help="Re-judge even when judgment file already exists",
    )
    p_judge.set_defaults(func=cmd_judge)

    p_report = sub.add_parser("report", help="Aggregate results into REPORT.md (free)")
    p_report.set_defaults(func=cmd_report)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
