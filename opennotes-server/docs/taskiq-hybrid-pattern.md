# Hybrid NATS → TaskIQ Pattern

This document describes the hybrid event-driven task processing pattern used in the content monitoring system.

## Overview

The hybrid pattern combines NATS JetStream for event routing with TaskIQ for reliable task execution:

```
Discord Bot          API Server              TaskIQ Worker
    │                    │                        │
    │  NATS Event        │                        │
    │ ─────────────────> │                        │
    │                    │  task.kiq()            │
    │                    │ ─────────────────────> │
    │                    │                        │ (execute task)
    │                    │                        │
```

## Why This Pattern?

See [ADR-004: NATS vs TaskIQ Usage Boundaries](../../backlog/decisions/ADR-004-nats-vs-taskiq-boundaries.md) for the full rationale.

### Summary

| Concern | NATS | TaskIQ |
|---------|------|--------|
| Cross-service events | ✅ | ❌ |
| Retries with backoff | ❌ | ✅ |
| Result storage | ❌ | ✅ |
| Distributed tracing | Partial | ✅ |
| Task scheduling | ❌ | ✅ |

## Implementation

### Task Definitions

All content monitoring tasks are defined in `src/tasks/content_monitoring_tasks.py`:

```python
@register_task(task_name="content:batch_scan", component="content_monitoring", task_type="batch")
async def process_bulk_scan_batch_task(
    scan_id: str,
    community_server_id: str,
    batch_number: int,
    messages: list[dict[str, Any]],
    db_url: str,
    redis_url: str,
) -> dict[str, Any]:
    # Task creates its own connections - self-contained for worker environment
    ...
```

### NATS Handler Dispatch

NATS handlers dispatch to TaskIQ tasks instead of processing directly:

```python
# src/bulk_content_scan/nats_handler.py
async def _handle_message_batch(self, event: BulkScanMessageBatchEvent) -> None:
    from src.tasks.content_monitoring_tasks import process_bulk_scan_batch_task

    # NATS handler dispatches to TaskIQ - lightweight, fast ack
    await process_bulk_scan_batch_task.kiq(
        scan_id=str(event.scan_id),
        community_server_id=str(event.community_server_id),
        batch_number=event.batch_number,
        messages=[msg.model_dump() for msg in event.messages],
        db_url=settings.DATABASE_URL,
        redis_url=settings.REDIS_URL,
    )
```

## Tasks

| Task | Purpose | Labels |
|------|---------|--------|
| `content:batch_scan` | Process bulk scan message batch | component=content_monitoring, task_type=batch |
| `content:finalize_scan` | Finalize scan and publish results | component=content_monitoring, task_type=finalize |
| `content:ai_note` | Generate AI-powered community notes | component=content_monitoring, task_type=generation |
| `content:vision_description` | Generate image descriptions via LLM | component=content_monitoring, task_type=vision |
| `content:audit_log` | Persist audit log entries | component=content_monitoring, task_type=audit |

## Key Design Decisions

### 1. Self-Contained Tasks

Tasks create their own database and Redis connections rather than relying on shared state:

```python
def _create_db_engine(db_url: str) -> Any:
    settings = get_settings()
    return create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        ...
    )
```

This ensures tasks work reliably in distributed worker environments.

### 2. Lazy Imports

Task modules use lazy imports (imports inside functions) to avoid import-time settings validation:

```python
async def process_bulk_scan_batch_task(...):
    # Lazy imports - avoid import-time settings validation
    from src.bulk_content_scan.service import BulkContentScanService
    from src.cache.redis_client import RedisClient
    ...
```

This prevents circular import issues and allows the module to be imported before settings are fully configured.

### 3. Dual Completion Trigger

For bulk scans, completion can be triggered from two paths:
1. **Batch task**: When a batch completes and all batches are transmitted
2. **All-batches-transmitted event**: When transmission completes and all batches are processed

```python
# In process_bulk_scan_batch_task
if transmitted and processed_count >= transmitted_messages:
    await finalize_bulk_scan_task.kiq(...)
```

This handles race conditions where transmission completes before processing.

### 4. OpenTelemetry Integration

All tasks create spans with consistent attributes:

```python
with _tracer.start_as_current_span("content.batch_scan") as span:
    span.set_attribute("task.scan_id", scan_id)
    span.set_attribute("task.component", "content_monitoring")
    ...
```

TaskIQ's OpenTelemetryMiddleware propagates trace context automatically.

### 5. Resource Cleanup

Tasks always clean up resources in `finally` blocks:

```python
try:
    async with async_session() as session:
        # ... task logic ...
finally:
    await redis_client.disconnect()
    await engine.dispose()
```

## Worker Configuration

TaskIQ workers are configured in infrastructure to load content monitoring tasks:

```hcl
# infrastructure/environments/local/main.tf
command = [
    "python", "-m", "taskiq", "worker",
    "src.tasks.broker:get_broker",
    "src.tasks.rechunk_tasks",
    "src.tasks.content_monitoring_tasks"
]
```

## Testing

- **Unit tests**: `tests/unit/test_content_monitoring_tasks.py` (14 tests)
- **Integration tests**: `tests/integration/test_taskiq_content_monitoring.py` (9 tests)

Tests use mocked dependencies and patch at source modules due to lazy imports.
