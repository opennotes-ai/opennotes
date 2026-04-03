# LLM Observability with Pydantic Logfire

This document describes the LLM observability setup using Pydantic Logfire in opennotes-server.

## Overview

Pydantic Logfire provides automatic instrumentation for LLM calls (OpenAI, Anthropic) with [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). Logfire serves as the unified OTel entry point, with Cloud Trace as an additional export destination. This enables:

- **Token usage tracking**: `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`
- **Model information**: `gen_ai.request.model`, `gen_ai.response.model`
- **Provider identification**: `gen_ai.system` (openai, anthropic, etc.)
- **Request/response tracing**: Full trace context for LLM calls
- **Dual export**: Spans ship to both Logfire dashboard and Google Cloud Trace

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGFIRE_ENABLED` | `true` | Enable/disable Logfire observability |
| `LOGFIRE_TOKEN` | - | Logfire write token for sending telemetry to logfire.dev |
| `LOGFIRE_TRACE_CONTENT` | `false` | Log prompts and completions in traces (disables scrubbing) |
| `ENABLE_TRACING` | `true` | Master switch for all tracing |

### Data Redaction

By default, `LOGFIRE_TRACE_CONTENT=false` enables Logfire's built-in scrubbing which redacts sensitive data from spans. When set to `true`, scrubbing is disabled to allow full prompt/completion content in traces. Enable content tracing only in development/debugging environments.

## Automatic Instrumentation

Logfire automatically instruments these LLM providers via `logfire.instrument_anthropic()` and `logfire.instrument_openai()`:
- **OpenAI**: `ChatCompletion.create`, `Embedding.create`
- **Anthropic**: `messages.create`

Infrastructure instrumentation uses OTel community instrumentors:
- **FastAPI**: HTTP request/response tracing
- **Redis**: Cache operation tracing
- **SQLAlchemy**: Database query tracing
- **HTTPX**: Outbound HTTP call tracing

No code changes required - instrumentation is applied at import time.

## Span Attributes

Each LLM span includes:

```
gen_ai.system: "openai"
gen_ai.request.model: "gpt-5-mini"
gen_ai.response.model: "gpt-5-mini"
gen_ai.usage.prompt_tokens: 150
gen_ai.usage.completion_tokens: 75
gen_ai.usage.total_tokens: 225
```

## Integration

Logfire is configured as the unified observability entry point via `setup_observability()` in `src/monitoring/observability.py`. Cloud Trace export is added via `additional_span_processors` to Logfire's TracerProvider.

```yaml
# .env.yaml
LOGFIRE_ENABLED: true
LOGFIRE_TOKEN: "your-logfire-write-token"
LOGFIRE_TRACE_CONTENT: false
ENABLE_TRACING: true
```

## Viewing LLM Traces

LLM traces appear in both Logfire dashboard (logfire.pydantic.dev) and Google Cloud Trace with:
- Span name: LLM operation name
- Parent context: Links to HTTP request that triggered the LLM call
- Duration: End-to-end latency for the LLM call
- Attributes: Token usage, model info, error details

## Troubleshooting

### LLM calls not appearing in traces

1. Verify `LOGFIRE_ENABLED=true` and `ENABLE_TRACING=true`
2. Check startup logs for "Observability initialized via Logfire"
3. Ensure `logfire` is installed: `uv pip list | grep logfire`

### Token counts showing zero

Some models/providers may not return usage data. This is provider-dependent.

### High cardinality issues

If using content tracing (`LOGFIRE_TRACE_CONTENT=true`), ensure your backend can handle large attribute values. Consider sampling for high-volume production use.
