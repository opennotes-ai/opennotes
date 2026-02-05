# LLM Observability with Traceloop

This document describes the LLM observability setup using Traceloop SDK in opennotes-server.

## Overview

Traceloop SDK provides automatic instrumentation for LLM calls (LiteLLM, OpenAI, Anthropic) with [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). This enables:

- **Token usage tracking**: `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`
- **Model information**: `gen_ai.request.model`, `gen_ai.response.model`
- **Provider identification**: `gen_ai.system` (openai, anthropic, etc.)
- **Request/response tracing**: Full trace context for LLM calls

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACELOOP_ENABLED` | `true` | Enable/disable Traceloop SDK |
| `TRACELOOP_TRACE_CONTENT` | `false` | Log prompts and completions in traces |
| `OTLP_ENDPOINT` | - | OTLP exporter endpoint (required) |
| `OTLP_HEADERS` | - | Headers for OTLP exporter (e.g., `Authorization=Bearer token`) |

### Data Redaction

By default, `TRACELOOP_TRACE_CONTENT=false` prevents logging of:
- Prompt content (`gen_ai.input.messages`)
- Completion content (`gen_ai.output.messages`)
- Embedding inputs

This ensures sensitive data is not stored in traces. Enable content tracing only in development/debugging environments.

## Automatic Instrumentation

Traceloop automatically instruments these libraries:
- **LiteLLM**: All `acompletion`, `aembedding` calls
- **OpenAI**: `ChatCompletion.create`, `Embedding.create`
- **Anthropic**: `messages.create`

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
traceloop.span.kind: "llm"
```

## Integration with Middleware

The OTLP endpoint and headers are shared with existing OpenTelemetry configuration:

```yaml
# .env.yaml
OTLP_ENDPOINT: "https://your-observability-backend/v1/traces"
OTLP_HEADERS: "Authorization=Bearer $MW_API_KEY"
TRACELOOP_ENABLED: true
TRACELOOP_TRACE_CONTENT: false
```

## Viewing LLM Traces

LLM traces appear in your observability backend with:
- Span name: `llm.completion` or `llm.embedding`
- Parent context: Links to HTTP request that triggered the LLM call
- Duration: End-to-end latency for the LLM call
- Attributes: Token usage, model info, error details

## Workflow Decorators (Optional)

For custom tracing of LLM workflows, use decorators:

```python
from traceloop.sdk.decorators import aworkflow

@aworkflow(name="generate_note")
async def generate_note(prompt: str) -> str:
    # Multiple LLM calls grouped under this workflow span
    ...
```

## Troubleshooting

### LLM calls not appearing in traces

1. Verify `TRACELOOP_ENABLED=true` and `OTLP_ENDPOINT` is set
2. Check startup logs for "Traceloop LLM observability enabled"
3. Ensure `traceloop-sdk` is installed: `uv pip list | grep traceloop`

### Token counts showing zero

Some models/providers may not return usage data. This is provider-dependent.

### High cardinality issues

If using content tracing (`TRACELOOP_TRACE_CONTENT=true`), ensure your backend can handle large attribute values. Consider sampling for high-volume production use.
