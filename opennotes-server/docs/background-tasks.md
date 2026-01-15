# Background Tasks with Taskiq

This document describes the background task system using [taskiq](https://taskiq-python.github.io/) with NATS JetStream as the message broker and Redis for result storage.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   FastAPI App   │────▶│  NATS JetStream  │────▶│  Taskiq Worker  │
│  (Task Dispatch)│     │   (Message Bus)  │     │ (Task Execution)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                                 ┌─────────────────┐
                                                 │     Redis       │
                                                 │  (Result Store) │
                                                 └─────────────────┘
```

- **FastAPI App**: Dispatches tasks using `.kiq()` method
- **NATS JetStream**: Reliable message delivery with persistence
- **Taskiq Worker**: Separate process that executes tasks
- **Redis**: Stores task results for retrieval

## Creating Tasks

Tasks are defined using the `@register_task()` decorator:

```python
from src.tasks.broker import register_task

@register_task()
async def my_background_task(arg1: str, arg2: int) -> str:
    # Do some work...
    return f"Processed: {arg1}, {arg2}"
```

### Task Names

By default, tasks are named using their module and function name (e.g., `src.tasks.example:example_task`). You can specify a custom name:

```python
@register_task(task_name="custom_name")
async def my_task():
    pass
```

## Dispatching Tasks

### From FastAPI Endpoints

```python
from src.tasks.example import example_task

@router.post("/process")
async def process_data(data: str):
    # Dispatch task for background processing
    task = await example_task.kiq(data)
    return {"task_id": task.task_id}
```

### Waiting for Results

```python
# Wait for result with timeout
result = await task.wait_result(timeout=30)

if not result.is_err:
    return {"result": result.return_value}
else:
    return {"error": result.error}
```

### Fire and Forget

```python
# Dispatch without waiting
await example_task.kiq("data")
```

## Running the Worker

### Development

Workers run as a dedicated container alongside the API server:

```bash
# Start all services including the worker
docker compose up

# Or start services individually
docker compose up opennotes-server   # API server
docker compose up opennotes-worker   # Taskiq worker
```

For local development without Docker:

```bash
# Run worker with auto-discovery of all *tasks.py modules
python -m taskiq worker src.tasks.broker:get_broker -fsd -tp "**/*tasks.py"

# Or with reload for development
python -m taskiq worker src.tasks.broker:get_broker -fsd -tp "**/*tasks.py" --reload
```

The `-fsd` (file system discovery) flag with `-tp` (task pattern) automatically discovers all task modules matching the `**/*tasks.py` pattern.

### Docker Compose

The `docker-compose.yml` defines separate services:

- `opennotes-server`: Runs the FastAPI API server only
- `opennotes-worker`: Runs the taskiq worker process

This architecture ensures:
- Clean separation of concerns
- Independent scaling of API and workers
- Workers don't compete with API for memory
- Easier debugging and monitoring

### Cloud Run

In production, workers run in a Cloud Run Worker Pool (see task-915):

- **opennotes-server**: Cloud Run Service for HTTP API
- **opennotes-worker**: Cloud Run Worker Pool for background processing

Worker pools are optimized for pull-based workloads like taskiq consumers.

## Configuration

The broker uses environment variables from `src.config`:

- `NATS_URL`: NATS server URL (default: `nats://localhost:4222`)
- `REDIS_URL`: Redis URL for result storage (default: `redis://localhost:6379/0`)
- `TASKIQ_STREAM_NAME`: NATS JetStream stream name (default: `OPENNOTES_TASKS`)
- `TASKIQ_RESULT_EXPIRY`: Time in seconds to keep results in Redis (default: `3600`)
- `TASKIQ_DEFAULT_RETRY_COUNT`: Number of automatic retries for failed tasks (default: `3`)

## Error Handling

Tasks that raise exceptions have their errors captured in the result:

```python
@register_task()
async def risky_task():
    raise ValueError("Something went wrong")

# When waiting for result
result = await task.wait_result(timeout=10)
if result.is_err:
    print(f"Task failed: {result.error}")
```

## Best Practices

1. **Keep tasks idempotent**: Tasks may be retried on failure
2. **Use appropriate timeouts**: Set reasonable `wait_result` timeouts
3. **Handle errors gracefully**: Check `result.is_err` before using `return_value`
4. **Separate concerns**: Run workers in separate processes/containers from the API
5. **Monitor task queues**: Use NATS monitoring tools to track queue depth

## Adding New Tasks

1. Create a new module following the `*tasks.py` naming convention (e.g., `src/tasks/my_tasks.py`)
2. Use the `@register_task()` decorator

That's it! The worker uses file system discovery (`-fsd`) to automatically find all modules matching `**/*tasks.py`.

Example:

```python
# src/tasks/my_tasks.py
from src.tasks.broker import register_task

@register_task()
async def process_webhook(payload: dict) -> bool:
    # Process webhook data
    return True
```

**Important:** Task files must end with `tasks.py` (plural) to be discovered:
- ✅ `my_tasks.py` - will be discovered
- ✅ `import_tasks.py` - will be discovered
- ❌ `my_task.py` - will NOT be discovered (singular)
- ❌ `tasks.py` - will NOT be discovered (missing prefix)
