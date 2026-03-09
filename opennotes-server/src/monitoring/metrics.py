from opentelemetry import metrics

meter = metrics.get_meter("opennotes-server", "1.0.0")

http_requests_total = meter.create_counter(
    "http.requests",
    description="Total HTTP requests",
    unit="1",
)

http_request_duration_seconds = meter.create_histogram(
    "http.request.duration",
    description="HTTP request duration in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

active_requests = meter.create_up_down_counter(
    "http.active_requests",
    description="Number of active HTTP requests",
    unit="1",
)

notes_scored_total = meter.create_counter(
    "notes.scored",
    description="Total number of notes scored",
    unit="1",
)

scoring_duration_seconds = meter.create_histogram(
    "scoring.duration",
    description="Duration of scoring operations in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

ratings_processed_total = meter.create_counter(
    "ratings.processed",
    description="Total number of ratings processed",
    unit="1",
)

webhook_events_total = meter.create_counter(
    "webhook.events",
    description="Total webhook events received",
    unit="1",
)

webhook_processing_duration_seconds = meter.create_histogram(
    "webhook.processing.duration",
    description="Duration of webhook processing in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

database_queries_total = meter.create_counter(
    "database.queries",
    description="Total database queries executed",
    unit="1",
)

database_query_duration_seconds = meter.create_histogram(
    "database.query.duration",
    description="Database query duration in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

redis_operations_total = meter.create_counter(
    "redis.operations",
    description="Total Redis operations",
    unit="1",
)

redis_operation_duration_seconds = meter.create_histogram(
    "redis.operation.duration",
    description="Redis operation duration in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

auth_attempts_total = meter.create_counter(
    "auth.attempts",
    description="Total authentication attempts",
    unit="1",
)

rate_limit_exceeded_total = meter.create_counter(
    "rate_limit.exceeded",
    description="Total rate limit exceeded events",
    unit="1",
)

task_processing_duration_seconds = meter.create_histogram(
    "task.processing.duration",
    description="Duration of background task processing in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
        300.0,
    ),
)

errors_total = meter.create_counter(
    "errors",
    description="Total errors by type",
    unit="1",
)

system_cpu_usage = meter.create_gauge(
    "system.cpu.usage",
    description="System CPU usage percentage",
    unit="percent",
)

system_memory_usage = meter.create_gauge(
    "system.memory.usage",
    description="System memory usage in bytes",
    unit="By",
)

system_memory_available = meter.create_gauge(
    "system.memory.available",
    description="System memory available in bytes",
    unit="By",
)

database_connections = meter.create_gauge(
    "database.connections",
    description="Number of active database connections",
    unit="1",
)

redis_connections = meter.create_gauge(
    "redis.connections",
    description="Number of active Redis connections",
    unit="1",
)

cache_hits_total = meter.create_counter(
    "cache.hits",
    description="Total cache hits",
    unit="1",
)

cache_misses_total = meter.create_counter(
    "cache.misses",
    description="Total cache misses",
    unit="1",
)

cache_operations_total = meter.create_counter(
    "cache.operations",
    description="Total cache operations",
    unit="1",
)

cache_operation_duration_seconds = meter.create_histogram(
    "cache.operation.duration",
    description="Cache operation duration in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

cache_size_items = meter.create_gauge(
    "cache.size",
    description="Current number of items in cache",
    unit="1",
)

cache_evictions_total = meter.create_counter(
    "cache.evictions",
    description="Total cache evictions",
    unit="1",
)

cache_hit_rate = meter.create_gauge(
    "cache.hit_rate",
    description="Cache hit rate percentage (hits / total requests)",
    unit="percent",
)

scoring_tier_active = meter.create_gauge(
    "scoring.tier.active",
    description="Currently active scoring tier level (0-5)",
    unit="1",
)

scoring_note_count = meter.create_gauge(
    "scoring.note_count",
    description="Total number of notes in the system for tier selection",
    unit="1",
)

scoring_tier_transitions = meter.create_counter(
    "scoring.tier.transitions",
    description="Total number of scoring tier transitions",
    unit="1",
)

scoring_operations_by_tier = meter.create_counter(
    "scoring.operations_by_tier",
    description="Total scoring operations by tier",
    unit="1",
)

scoring_duration_by_tier = meter.create_histogram(
    "scoring.duration_by_tier",
    description="Scoring operation duration by tier in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

scoring_failures_by_tier = meter.create_counter(
    "scoring.failures_by_tier",
    description="Total scoring failures by tier",
    unit="1",
)

scoring_data_confidence = meter.create_gauge(
    "scoring.data_confidence",
    description="Data confidence level for scoring (0=none, 1=low, 2=medium, 3=high, 4=very_high)",
    unit="1",
)

bayesian_scorer_invocations_total = meter.create_counter(
    "bayesian.scorer.invocations",
    description="Total invocations of BayesianAverageScorer",
    unit="1",
)

bayesian_rating_count_distribution = meter.create_histogram(
    "bayesian.rating_count.distribution",
    description="Distribution of rating counts when scoring with Bayesian Average",
    unit="1",
    explicit_bucket_boundaries_advisory=(0, 1, 2, 3, 5, 10, 20, 50, 100),
)

bayesian_score_deviation_from_prior = meter.create_histogram(
    "bayesian.score_deviation_from_prior",
    description="Absolute deviation of calculated score from prior mean",
    unit="1",
    explicit_bucket_boundaries_advisory=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
)

bayesian_prior_updates_total = meter.create_counter(
    "bayesian.prior.updates",
    description="Total number of prior mean updates from system average",
    unit="1",
)

bayesian_prior_value = meter.create_gauge(
    "bayesian.prior.value",
    description="Current prior mean value (m parameter)",
    unit="1",
)

bayesian_provisional_scores_total = meter.create_counter(
    "bayesian.provisional_scores",
    description="Total number of provisional scores (rating_count < min_ratings_for_confidence)",
    unit="1",
)

bayesian_no_data_scores_total = meter.create_counter(
    "bayesian.no_data_scores",
    description="Total number of scores with zero ratings (returns prior mean)",
    unit="1",
)

bayesian_rating_clamp_events_total = meter.create_counter(
    "bayesian.rating_clamp_events",
    description="Total number of rating values clamped to valid range [0, 1]",
    unit="1",
)

bayesian_scoring_duration_seconds = meter.create_histogram(
    "bayesian.scoring.duration",
    description="Duration of Bayesian Average score calculation in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

bayesian_fallback_activations_total = meter.create_counter(
    "bayesian.fallback_activations",
    description="Total number of fallback activations due to errors (returns prior mean)",
    unit="1",
)

nats_events_published_total = meter.create_counter(
    "nats.events.published",
    description="Total NATS events published",
    unit="1",
)

nats_duplicate_events_total = meter.create_counter(
    "nats.events.duplicate",
    description="Total duplicate NATS events detected by JetStream",
    unit="1",
)

nats_publish_duration_seconds = meter.create_histogram(
    "nats.publish.duration",
    description="Duration of NATS publish operations in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

nats_events_failed_total = meter.create_counter(
    "nats.events.failed",
    description="Total NATS events that failed to publish after all retries",
    unit="1",
)

middleware_execution_duration_seconds = meter.create_histogram(
    "middleware.execution.duration",
    description="Total middleware execution time including all middleware layers",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

cors_preflight_requests_total = meter.create_counter(
    "cors.preflight_requests",
    description="Total CORS preflight OPTIONS requests received",
    unit="1",
)

encryption_key_age_days = meter.create_gauge(
    "encryption.key_age",
    description="Age of encryption key in days by configuration",
    unit="d",
)

encryption_key_rotations_total = meter.create_counter(
    "encryption.key_rotations",
    description="Total number of encryption key rotations",
    unit="1",
)

encryption_key_age_alerts_total = meter.create_counter(
    "encryption.key_age_alerts",
    description="Total number of encryption key age alerts triggered",
    unit="1",
)

encryption_keys_needing_rotation = meter.create_gauge(
    "encryption.keys_needing_rotation",
    description="Number of encryption keys that are due for rotation",
    unit="1",
)

ai_notes_generated_total = meter.create_counter(
    "ai.notes.generated",
    description="Total number of AI-generated notes",
    unit="1",
)

ai_notes_failed_total = meter.create_counter(
    "ai.notes.failed",
    description="Total number of failed AI note generation attempts",
    unit="1",
)

ai_note_generation_duration_seconds = meter.create_histogram(
    "ai.note_generation.duration",
    description="Duration of AI note generation in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

bulk_scan_finalization_dispatch_total = meter.create_counter(
    "bulk_scan.finalization_dispatch",
    description="Total bulk scan finalization dispatch attempts by outcome",
    unit="1",
)

relevance_check_total = meter.create_counter(
    "relevance_check",
    description="Total LLM relevance check outcomes",
    unit="1",
)

search_analytics_failures_total = meter.create_counter(
    "search_analytics.failures",
    description="Total failures when logging search analytics to Redis",
    unit="1",
)

semaphore_release_failures_total = meter.create_counter(
    "semaphore.release_failures",
    description="Total semaphore release failures after all retries exhausted",
    unit="1",
)

semaphore_release_retries_total = meter.create_counter(
    "semaphore.release_retries",
    description="Total semaphore release retry attempts",
    unit="1",
)

semaphore_leak_prevented_total = meter.create_counter(
    "semaphore.leak_prevented",
    description="Total semaphore leaks prevented by checking existing task_id tracking",
    unit="1",
)

batch_job_stuck_count = meter.create_gauge(
    "batch_job.stuck_count",
    description="Number of batch jobs stuck in non-terminal state with zero progress",
    unit="1",
)

batch_job_stuck_duration_seconds = meter.create_gauge(
    "batch_job.stuck_duration",
    description="Duration in seconds that batch jobs have been stuck (max across stuck jobs)",
    unit="s",
)

batch_job_stale_cleanup_total = meter.create_counter(
    "batch_job.stale_cleanup",
    description="Total number of stale batch jobs cleaned up by scheduled task",
    unit="1",
)

audit_events_published_total = meter.create_counter(
    "audit.events.published",
    description="Total number of audit events persisted via DBOS",
    unit="1",
)

audit_publish_failures_total = meter.create_counter(
    "audit.publish.failures",
    description="Total number of failed audit event persist operations",
    unit="1",
)

audit_publish_timeouts_total = meter.create_counter(
    "audit.publish.timeouts",
    description="Total number of audit event persist timeouts",
    unit="1",
)

dbos_pickle_fallback_total = meter.create_counter(
    "dbos.pickle_fallback",
    description="Number of times DBOS deserialization fell back to pickle from JSON",
    unit="1",
)

taskiq_task_duration_seconds = meter.create_histogram(
    "taskiq.task.duration",
    description="Duration of TaskIQ task execution in seconds",
    unit="s",
    explicit_bucket_boundaries_advisory=(
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
        300.0,
    ),
)

taskiq_tasks_total = meter.create_counter(
    "taskiq.tasks",
    description="Total TaskIQ tasks executed",
    unit="1",
)
