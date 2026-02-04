# Known Issues

This document tracks known issues, expected behaviors, and upstream limitations that may appear in logs or monitoring but do not require immediate action.

## DBOS Notification Listener Connection Drops

**Status:** Known issue, low priority
**Impact:** Warning logs every ~20 minutes, auto-recovers in ~1 second
**First observed:** 2026-01

### Symptom

The DBOS worker logs PostgreSQL notification listener errors approximately every 20 minutes:

```
Notification listener error: consuming input failed: server closed the connection unexpectedly
```

This is followed by an immediate reconnection (typically within 1 second).

### Root Cause

DBOS uses a dedicated psycopg connection for PostgreSQL LISTEN/NOTIFY to coordinate workflow execution. This connection:

1. Is separate from the main SQLAlchemy connection pool
2. Has no TCP keepalive parameters configured
3. Remains idle between notification events

Cloud database providers (including Supabase, which we use) terminate idle connections after a timeout period (typically 10-30 minutes) to manage resources. When the notification listener connection is terminated:

1. The next `poll()` call fails with "server closed the connection unexpectedly"
2. DBOS catches this error and logs the warning
3. DBOS automatically creates a new notification listener connection
4. Normal operation resumes within ~1 second

### Why This Is Not a Problem

1. **Auto-recovery:** DBOS handles this gracefully with automatic reconnection
2. **No data loss:** Workflow state is persisted in the database, not in the notification channel
3. **Minimal latency:** Reconnection takes ~1 second
4. **Expected behavior:** This is a natural consequence of cloud infrastructure connection management

### Potential Future Improvements

The ideal fix would be for DBOS to expose a `notification_connection_args` configuration option, allowing users to set TCP keepalive parameters:

```python
# Hypothetical future configuration
DBOS(
    notification_connection_args={
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)
```

### Upstream References

- **DBOS Issue #562:** [Handle missing notifications in recv/get_event](https://github.com/dbos-inc/dbos-transact-py/issues/562) - Related issue about notification handling, though focused on Postgres crash scenarios rather than idle connection timeouts
- **DBOS Issue #139:** [Scheduled workflow does not recover from database connection outage?](https://github.com/dbos-inc/dbos-transact-py/issues/139) - Historical issue about connection outage recovery (closed, but demonstrates DBOS's focus on connection resilience)

### Recommendation

**No action required.** The current behavior is acceptable:

1. The warning logs are informational, not errors
2. Auto-recovery works reliably
3. Impact is limited to brief (~1s) notification delays every ~20 minutes

If log verbosity becomes a concern, consider adding a log filter to suppress these specific warnings in production monitoring dashboards.
