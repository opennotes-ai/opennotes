#!/usr/bin/env python3
"""Benchmark database query latency.

Runs N simple SELECT 1 queries and reports p50, p95, p99 latency.
Use to measure per-query database latency.

Regression threshold: p99 should not exceed 200ms for SELECT 1.

Usage:
    uv run python scripts/benchmark_db_latency.py
    uv run python scripts/benchmark_db_latency.py --queries 200
    uv run python scripts/benchmark_db_latency.py --url postgresql+asyncpg://user:pass@host:5432/db
"""

import argparse
import asyncio
import statistics
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

P99_THRESHOLD_MS = 200.0


def percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


async def run_benchmark(database_url: str, num_queries: int) -> list[float]:
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        },
    )

    latencies: list[float] = []

    try:
        for i in range(num_queries):
            start = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

            if (i + 1) % 25 == 0:
                print(f"  Completed {i + 1}/{num_queries} queries...")
    finally:
        await engine.dispose()

    return latencies


def print_results(latencies: list[float]) -> None:
    if not latencies:
        print("No latency data collected.")
        return

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    mean = statistics.mean(latencies)
    std = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

    print()
    print("=" * 50)
    print("  Database Latency Benchmark Results")
    print("=" * 50)
    print(f"  Queries:  {len(latencies)}")
    print(f"  Mean:     {mean:.2f} ms")
    print(f"  Std Dev:  {std:.2f} ms")
    print(f"  Min:      {min(latencies):.2f} ms")
    print(f"  Max:      {max(latencies):.2f} ms")
    print("-" * 50)
    print(f"  p50:      {p50:.2f} ms")
    print(f"  p95:      {p95:.2f} ms")
    print(f"  p99:      {p99:.2f} ms")
    print("-" * 50)

    if p99 > P99_THRESHOLD_MS:
        print(f"  REGRESSION: p99 ({p99:.2f}ms) exceeds threshold ({P99_THRESHOLD_MS}ms)")
    else:
        print(f"  PASS: p99 ({p99:.2f}ms) within threshold ({P99_THRESHOLD_MS}ms)")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark database query latency")
    parser.add_argument(
        "--queries", "-n", type=int, default=100, help="Number of queries to run (default: 100)"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Database URL (default: read from settings/DATABASE_URL)",
    )
    args = parser.parse_args()

    database_url = args.url
    if database_url is None:
        from src.config import get_settings

        database_url = get_settings().DATABASE_URL

    print(f"Running {args.queries} SELECT 1 queries...")
    latencies = asyncio.run(run_benchmark(database_url, args.queries))
    print_results(latencies)


if __name__ == "__main__":
    main()
