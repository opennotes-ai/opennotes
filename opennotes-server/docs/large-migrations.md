# Large Data Migrations

Strategies for migrations that touch many rows without hitting statement timeouts.

## Batched Updates (Python-side)

Use when updating existing rows. Each batch runs as a separate statement.

```python
def _batch_update_field(batch_size: int = 5000) -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text("SELECT COUNT(*) FROM table WHERE condition"))
    total = result.scalar() or 0
    if total == 0:
        return

    print(f"Updating {total} rows in batches of {batch_size}")

    batch_num = 0
    while True:
        result = conn.execute(
            sa.text("""
                UPDATE table SET column = new_value
                WHERE id IN (
                    SELECT id FROM table WHERE condition LIMIT :batch_size
                )
            """),
            {"batch_size": batch_size},
        )
        if result.rowcount == 0:
            break
        batch_num += 1
        print(f"Batch {batch_num}: {result.rowcount} rows")

    print(f"Done: {batch_num} batches")
```

## Key Points

- **Batch size**: 1000-5000 rows typical. Tune based on row size and timeout.
- **Progress logging**: Use `print()` for visibility in migration output.
- **Subquery LIMIT**: Selects batch by ID, then updates matching rows.
- **No COMMIT**: Alembic handles transaction. Batches are separate statements within same transaction.
- **Idempotent WHERE**: Ensures re-running picks up remaining rows (e.g., `WHERE column = old_value`).

## When to Batch

- UPDATEs touching >10k rows
- Any operation that might exceed statement timeout (Supabase: ~60s default)
- Backfilling new columns with computed values

## When NOT to Batch

- Schema changes (ADD COLUMN, CREATE INDEX) - these are atomic
- Small tables (<10k rows)
- Simple value updates (SET column = constant)
