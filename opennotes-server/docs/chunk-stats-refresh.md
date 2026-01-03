# chunk_stats Materialized View Refresh Strategy

## Overview

The `chunk_stats` materialized view provides aggregated corpus statistics for BM25/TF-IDF scoring in the PGroonga full-text search system. It stores:

- `total_chunks`: Total number of chunks with word_count > 0
- `avg_chunk_length`: Average word count across all chunks

These statistics are used for document length normalization in BM25 scoring.

## Why Refresh is Needed

Materialized views cache their query results and don't automatically update when the underlying table changes. As new chunks are added or existing chunks are modified, the statistics become stale.

**Impact of stale statistics:**
- BM25 length normalization becomes less accurate
- Scores may favor documents of certain lengths disproportionately
- Impact is gradual and typically minor for large corpora

## Refresh Strategy

### Recommended: Nightly Concurrent Refresh

Refresh the view once daily during low-traffic hours (e.g., 3:00 AM UTC):

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats;
```

**Why CONCURRENTLY?**
- Does not block reads on the materialized view during refresh
- Requires a unique index (already created: `idx_chunk_stats_unique`)
- Takes slightly longer but maintains availability

### Alternative: Blocking Refresh

For maintenance windows or when reads can be paused:

```sql
REFRESH MATERIALIZED VIEW chunk_stats;
```

Faster than concurrent refresh but blocks all reads during execution.

## Implementation Options

### Option 1: pg_cron (Recommended for Production)

If using pg_cron extension:

```sql
SELECT cron.schedule(
    'refresh-chunk-stats',
    '0 3 * * *',  -- 3:00 AM daily
    'REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats'
);
```

### Option 2: External Scheduler (Cloud Run Jobs, Kubernetes CronJob)

Create a scheduled job that executes:

```bash
psql $DATABASE_URL -c "REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats;"
```

### Option 3: Application-Level Scheduler

Add a TaskIQ scheduled task (requires scheduler infrastructure):

```python
from taskiq import TaskiqScheduler
from src.tasks.broker import register_task

@register_task(task_name="maintenance:refresh_chunk_stats")
async def refresh_chunk_stats(db_url: str) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats"))
    await engine.dispose()
    return {"status": "refreshed"}
```

## Monitoring

### Check Last Refresh Time

PostgreSQL does not track materialized view refresh times natively. Options:

1. **Wrap refresh in a logging function:**

```sql
CREATE OR REPLACE FUNCTION refresh_chunk_stats_with_log()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY chunk_stats;
    INSERT INTO maintenance_log (view_name, refreshed_at)
    VALUES ('chunk_stats', NOW())
    ON CONFLICT (view_name) DO UPDATE SET refreshed_at = NOW();
END;
$$ LANGUAGE plpgsql;
```

2. **Check via application metrics:**
   - Log refresh completion with timestamp
   - Emit Prometheus metric on successful refresh

### Verify Statistics

```sql
SELECT * FROM chunk_stats;
```

Compare with live counts:

```sql
SELECT
    COUNT(*) AS actual_total,
    AVG(word_count)::float AS actual_avg
FROM chunk_embeddings
WHERE word_count > 0;
```

## Staleness Tolerance

For typical use cases:
- **Daily refresh**: Sufficient for most applications
- **Hourly refresh**: For high-velocity ingestion or strict accuracy needs
- **Manual refresh**: After bulk data migrations or imports

The BM25 algorithm is robust to minor statistical drift. A 5-10% change in corpus statistics has minimal impact on ranking quality.
