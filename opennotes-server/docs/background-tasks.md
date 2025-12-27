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

```bash
# Run worker separately
taskiq worker src.tasks.broker:broker src.tasks.example

# Or with uvicorn reload
taskiq worker src.tasks.broker:broker src.tasks.example --reload
```

### Docker

Set the `RUN_MODE` environment variable:

```bash
# API server only (default)
RUN_MODE=server ./docker-entrypoint.sh

# Worker only
RUN_MODE=worker ./docker-entrypoint.sh

# Both server and worker in same container
RUN_MODE=both ./docker-entrypoint.sh
```

### Kubernetes

For production, run separate deployments:

```yaml
# API Server Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opennotes-server
spec:
  template:
    spec:
      containers:
        - name: server
          env:
            - name: RUN_MODE
              value: "server"

---
# Worker Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opennotes-worker
spec:
  template:
    spec:
      containers:
        - name: worker
          env:
            - name: RUN_MODE
              value: "worker"
```

## Configuration

The broker uses environment variables from `src.config`:

- `NATS_URL`: NATS server URL (default: `nats://localhost:4222`)
- `REDIS_URL`: Redis URL for result storage (default: `redis://localhost:6379/0`)

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

1. Create a new module or add to `src/tasks/example.py`
2. Use the `@register_task()` decorator
3. Import the module in the worker command (add to `taskiq worker` args)
4. Update the Docker entrypoint if needed

Example:

```python
# src/tasks/my_tasks.py
from src.tasks.broker import register_task

@register_task()
async def process_webhook(payload: dict) -> bool:
    # Process webhook data
    return True
```

Update worker command:
```bash
taskiq worker src.tasks.broker:broker src.tasks.example src.tasks.my_tasks
```
