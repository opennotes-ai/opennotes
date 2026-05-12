# Vibecheck Shared Limiter Contract

This contract pins the Redis protocol for the dedicated Vibecheck limiter
Memorystore instance. It is consumed by the TypeScript `vibecheck-web`
analyze-submit request limiter and the Python `vibecheck-server`
Vertex/Gemini concurrency limiter.

The limiter backend is intentionally separate from generic `REDIS_URL`.
Clients must use only these dedicated settings:

- `VIBECHECK_LIMITER_REDIS_URL`: Secret Manager-backed Redis URL.
- `VIBECHECK_LIMITER_REDIS_CA_CERT_PATH`: mounted CA certificate path.
- CA mount path in production: `/etc/ssl/vibecheck-limiter-redis/ca.crt`.

Production Memorystore uses AUTH and `SERVER_AUTHENTICATION`; clients must
connect with TLS, verify the mounted CA, and fail startup/config validation if
the limiter URL is configured without TLS in production.

## Shared Requirements

- All keys start with `vibecheck:rl:` and include the primitive name.
- Hash user/IP identifiers before they enter keys or logs.
- Use Redis server time inside Lua scripts when expiration math matters.
- No client should use Redis transactions assembled from separate round trips
  for limiter state changes. Use Lua scripts or single Redis commands with
  equivalent atomicity.
- Redis command timeout target: 10 ms. One retry is allowed only for transport
  errors before the primitive-specific failure behavior runs.
- Added p99 latency budget: less than 20 ms per limiter decision in the request
  path, measured around Redis acquire/check/release calls.
- Structured logs must include `limiter_backend="vibecheck-limiter-redis"`,
  `limiter_consumer`, `limiter_primitive`, `limiter_result`, `fail_open`, and
  `error_class` when applicable.
- Metrics must distinguish backend errors from deny/saturation outcomes.
- Generic `REDIS_URL` is not part of this contract.

## Request Bucket Primitive

Consumer: `vibecheck-web` analyze submit guard.

Keys:

- Client bucket: `vibecheck:rl:web:analyze:client:<hashed-client>`
- Global unattributable bucket: `vibecheck:rl:web:analyze:global:<window-id>`

The client hash should be generated from the best available stable client
identifier plus a server-side salt. Never store raw IP addresses, user agents,
or cookies in Redis keys.

Behavior:

- Fixed-window counter.
- A single Lua script increments the bucket, sets TTL only on the first hit,
  and returns the full decision.
- First hit: `INCR key`, then `PEXPIRE key window_ms`.
- Later hits: preserve existing TTL; if the key unexpectedly has no TTL, set
  it to the current window.
- The decision denies when the post-increment count is greater than `limit`.
- The response shape is:
  - `allowed`: boolean
  - `limit`: number
  - `remaining`: number, floor at `0`
  - `retry_after_ms`: number
  - `reset_at_ms`: Unix epoch milliseconds
  - `count`: number

Failure behavior:

- Backend unavailability may fail open for legitimate analyze submits.
- Fail-open decisions must emit a warning log with
  `alert_type="ratelimit_backend_unavailable"`,
  `limiter_consumer="web_analyze"`,
  `limiter_primitive="fixed_window_bucket"`, and `fail_open=true`.
- Emit a metric sample for backend unavailability. The metric must be suitable
  for a Cloud Logging filter or alert keyed by `alert_type`.
- Do not fail open for malformed configuration, missing TLS CA in production,
  or script/serialization bugs that prove the client cannot interpret decisions.

## Vertex/Gemini Lease Primitive

Consumer: `vibecheck-server` Vertex/Gemini model calls.

Keys:

- Slot set: `vibecheck:rl:vertex:slots`
- Lease token key: `vibecheck:rl:vertex:lease:<token>`
- Optional wait queue or diagnostic key prefix:
  `vibecheck:rl:vertex:pending:<hashed-job-or-request>`

Behavior:

- Distributed bounded semaphore.
- Acquire and release are atomic Lua scripts.
- Each acquire request supplies a unique random token and lease TTL.
- Acquire removes expired slot entries, checks active count, and either inserts
  the token with an expiration score or returns saturated metadata.
- Release succeeds only when the caller owns the token. A release for an
  unknown or expired token is a no-op with `released=false`.
- Lease TTL must be long enough for expected Gemini calls plus cleanup margin.
  Implementations should renew long-running leases before half the TTL remains.
- Orphan recovery is TTL-based: expired tokens are removed on every acquire and
  may also be removed by a low-frequency cleanup path.
- Saturation uses bounded wait/backoff with jitter. The caller may wait only up
  to its operation budget, then fails with an explicit saturation result rather
  than opening extra slots.
- Metrics map to the current in-process limiter:
  - active slots: cardinality of the slot set after cleanup
  - pending waiters: callers currently sleeping/backing off
  - acquire latency: time from first attempt to acquired or saturated
  - saturation count: attempts that exhausted their bounded wait

Acquire response shape:

- `acquired`: boolean
- `token`: string when acquired
- `active`: number
- `limit`: number
- `lease_ttl_ms`: number
- `retry_after_ms`: number when saturated
- `reason`: `acquired`, `saturated`, or `backend_unavailable`

Release response shape:

- `released`: boolean
- `token`: string
- `active`: number after release cleanup
- `reason`: `released`, `not_owner_or_expired`, or `backend_unavailable`

Failure behavior:

- Do not blindly fail open. This primitive protects Gemini quota and spend.
- Preferred behavior is fail closed with bounded retry/backoff, returning a
  structured limiter error when the backend stays unavailable.
- A degraded local fallback is allowed only when it is explicitly capped below
  the distributed limit and emits warning logs and metrics with
  `limiter_consumer="vertex_gemini"`,
  `limiter_primitive="distributed_lease"`,
  `limiter_result="degraded_local_fallback"`, and `fail_open=false`.
- Backend unavailability logs must include
  `alert_type="ratelimit_backend_unavailable"` and `fail_open=false`.
- `vibecheck_max_instances` must remain `1` until the shared lease client is
  implemented, deployed, and production-verified.

## Implementation Notes

- The infrastructure task that provides this backend is `TASK-1483.31.01`.
- The web client implementation is `TASK-1483.12.02`.
- The Vertex/Gemini migration is `TASK-1483.16.08`.
- Operators should verify clients read `VIBECHECK_LIMITER_REDIS_URL` and never
  fall back to generic `REDIS_URL` for these primitives.
