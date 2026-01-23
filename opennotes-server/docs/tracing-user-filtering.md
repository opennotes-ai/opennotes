# Filtering Traces by User in Cloud Trace

This document explains how to filter distributed traces by user in Google Cloud Trace
to debug user-specific issues.

## Span Attributes for User Context

The OpenNotes server attaches the following span attributes for user identification:

### Standard Attributes (JWT-authenticated requests)

| Attribute | Description | Example |
|-----------|-------------|---------|
| `enduser.id` | User's UUID (standard OTel semantic convention) | `550e8400-e29b-41d4-a716-446655440000` |
| `user.username` | User's username | `johndoe` |
| `enduser.role` | User's role from JWT | `user`, `moderator`, `admin` |

### Discord-specific Attributes (Discord bot requests)

| Attribute | Description | Example |
|-----------|-------------|---------|
| `discord.user_id` | Discord snowflake ID | `123456789012345678` |
| `discord.username` | Discord username | `johndoe#1234` |
| `discord.guild_id` | Discord server ID | `987654321098765432` |

### Event Handler Attributes (NATS consumers)

| Attribute | Description |
|-----------|-------------|
| `event.initiator.user_id` | User who triggered the event |

## Cloud Trace Filter Syntax

In the Google Cloud Console, navigate to:
**Cloud Trace > Trace list** or use the [Cloud Trace Explorer](https://console.cloud.google.com/traces/list)

### Basic Filters

Filter traces by standard user ID:
```
+enduser.id:550e8400-e29b-41d4-a716-446655440000
```

Filter traces by Discord user ID:
```
+discord.user_id:123456789012345678
```

Filter traces by username:
```
+user.username:johndoe
```

### Combining Filters

Find traces for a specific user that were slow (> 500ms):
```
+enduser.id:550e8400-e29b-41d4-a716-446655440000 latency:>500ms
```

Find error traces for a specific Discord user:
```
+discord.user_id:123456789012345678 status:ERROR
```

Find traces for a user in a specific Discord server:
```
+discord.user_id:123456789012345678 +discord.guild_id:987654321098765432
```

## Common Debugging Scenarios

### 1. User Reports Slow Performance

1. Get the user's ID (from database or logs)
2. Filter by user and sort by latency:
   ```
   +enduser.id:<user-uuid>
   ```
3. Sort results by latency descending
4. Examine the slowest traces for bottlenecks

### 2. User Reports an Error

1. Get the user's ID
2. Filter for error traces:
   ```
   +enduser.id:<user-uuid> status:ERROR
   ```
3. Click on trace to see error details and stack traces

### 3. Correlating Events and Background Tasks

When a user action triggers background processing (via NATS events or Taskiq tasks),
the trace context is propagated. Look for:
- `event.initiator.user_id` on event consumer spans
- Parent-child relationships linking HTTP requests to background processing

### 4. Discord Bot Issues

For issues reported in Discord:
1. Get the Discord user's ID (right-click > Copy User ID with Developer Mode)
2. Filter:
   ```
   +discord.user_id:<discord-snowflake>
   ```

## Trace Context Propagation

User context is propagated across service boundaries via:

1. **W3C Baggage**: Standard propagation header for distributed systems
2. **NATS Headers**: Explicit `X-User-Id`, `X-Username`, `X-Discord-User-Id` headers
3. **Taskiq Context**: Inherited from parent span via OpenTelemetry middleware

This ensures user attribution is maintained across:
- HTTP API requests
- NATS event publishing and consuming
- Background task execution (Taskiq workers)

## Troubleshooting

### No User Attributes in Trace

If spans are missing user attributes:

1. **Authentication issue**: The request may not have a valid JWT token
2. **Middleware order**: Ensure `AuthenticatedUserContextMiddleware` is registered
3. **Tracing disabled**: Check `ENABLE_TRACING` environment variable

### Different User IDs

- `enduser.id`: Application user UUID (from database)
- `discord.user_id`: Discord snowflake ID (external identifier)

These may both be present if the user authenticated via JWT and the request
originated from the Discord bot (which sets X-Discord-* headers).
