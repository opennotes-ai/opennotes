from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.core import CollectorRegistry

__all__ = ["CollectorRegistry", "Counter", "Gauge", "Histogram", "generate_latest", "registry"]

registry = CollectorRegistry()


def _get_instance_labels() -> list[str]:
    return ["instance_id"]


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status", "instance_id"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "instance_id"],
    registry=registry,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

active_requests = Gauge(
    "active_requests",
    "Number of active HTTP requests",
    ["instance_id"],
    registry=registry,
)

notes_scored_total = Counter(
    "notes_scored_total",
    "Total number of notes scored",
    ["status", "instance_id"],
    registry=registry,
)

scoring_duration_seconds = Histogram(
    "scoring_duration_seconds",
    "Duration of scoring operations in seconds",
    ["instance_id"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

ratings_processed_total = Counter(
    "ratings_processed_total",
    "Total number of ratings processed",
    ["instance_id"],
    registry=registry,
)

webhook_events_total = Counter(
    "webhook_events_total",
    "Total webhook events received",
    ["event_type", "status", "instance_id"],
    registry=registry,
)

webhook_processing_duration_seconds = Histogram(
    "webhook_processing_duration_seconds",
    "Duration of webhook processing in seconds",
    ["event_type", "instance_id"],
    registry=registry,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

database_queries_total = Counter(
    "database_queries_total",
    "Total database queries executed",
    ["operation", "table", "instance_id"],
    registry=registry,
)

database_query_duration_seconds = Histogram(
    "database_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table", "instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

redis_operations_total = Counter(
    "redis_operations_total",
    "Total Redis operations",
    ["operation", "status", "instance_id"],
    registry=registry,
)

redis_operation_duration_seconds = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation duration in seconds",
    ["operation", "instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)

auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total authentication attempts",
    ["method", "status", "instance_id"],
    registry=registry,
)

rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total rate limit exceeded events",
    ["endpoint", "instance_id"],
    registry=registry,
)

task_processing_duration_seconds = Histogram(
    "task_processing_duration_seconds",
    "Duration of background task processing in seconds",
    ["task_type", "instance_id"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

errors_total = Counter(
    "errors_total",
    "Total errors by type",
    ["error_type", "endpoint", "instance_id"],
    registry=registry,
)

system_cpu_usage = Gauge(
    "system_cpu_usage_percent",
    "System CPU usage percentage",
    ["instance_id"],
    registry=registry,
)

system_memory_usage = Gauge(
    "system_memory_usage_bytes",
    "System memory usage in bytes",
    ["instance_id"],
    registry=registry,
)

system_memory_available = Gauge(
    "system_memory_available_bytes",
    "System memory available in bytes",
    ["instance_id"],
    registry=registry,
)

database_connections = Gauge(
    "database_connections",
    "Number of active database connections",
    ["state", "instance_id"],
    registry=registry,
)

redis_connections = Gauge(
    "redis_connections",
    "Number of active Redis connections",
    ["state", "instance_id"],
    registry=registry,
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type", "key_prefix", "instance_id"],
    registry=registry,
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type", "key_prefix", "instance_id"],
    registry=registry,
)

cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["cache_type", "operation", "status", "instance_id"],
    registry=registry,
)

cache_operation_duration_seconds = Histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["cache_type", "operation", "instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

cache_size_items = Gauge(
    "cache_size_items",
    "Current number of items in cache",
    ["cache_type", "instance_id"],
    registry=registry,
)

cache_evictions_total = Counter(
    "cache_evictions_total",
    "Total cache evictions",
    ["cache_type", "reason", "instance_id"],
    registry=registry,
)

cache_hit_rate = Gauge(
    "cache_hit_rate_percent",
    "Cache hit rate percentage (hits / total requests)",
    ["cache_type", "instance_id"],
    registry=registry,
)

scoring_tier_active = Gauge(
    "scoring_tier_active_level",
    "Currently active scoring tier level (0-5)",
    ["instance_id"],
    registry=registry,
)

scoring_note_count = Gauge(
    "scoring_note_count_total",
    "Total number of notes in the system for tier selection",
    ["instance_id"],
    registry=registry,
)

scoring_tier_transitions = Counter(
    "scoring_tier_transitions_total",
    "Total number of scoring tier transitions",
    ["from_tier", "to_tier", "instance_id"],
    registry=registry,
)

scoring_operations_by_tier = Counter(
    "scoring_operations_by_tier_total",
    "Total scoring operations by tier",
    ["tier_level", "tier_name", "instance_id"],
    registry=registry,
)

scoring_duration_by_tier = Histogram(
    "scoring_duration_by_tier_seconds",
    "Scoring operation duration by tier in seconds",
    ["tier_level", "tier_name", "instance_id"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

scoring_failures_by_tier = Counter(
    "scoring_failures_by_tier_total",
    "Total scoring failures by tier",
    ["tier_level", "tier_name", "error_type", "instance_id"],
    registry=registry,
)

scoring_data_confidence = Gauge(
    "scoring_data_confidence_level",
    "Data confidence level for scoring (0=none, 1=low, 2=medium, 3=high, 4=very_high)",
    ["instance_id"],
    registry=registry,
)

bayesian_scorer_invocations_total = Counter(
    "bayesian_scorer_invocations_total",
    "Total invocations of BayesianAverageScorer",
    ["instance_id"],
    registry=registry,
)

bayesian_rating_count_distribution = Histogram(
    "bayesian_rating_count_distribution",
    "Distribution of rating counts when scoring with Bayesian Average",
    ["instance_id"],
    registry=registry,
    buckets=(0, 1, 2, 3, 5, 10, 20, 50, 100),
)

bayesian_score_deviation_from_prior = Histogram(
    "bayesian_score_deviation_from_prior",
    "Absolute deviation of calculated score from prior mean",
    ["instance_id"],
    registry=registry,
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
)

bayesian_prior_updates_total = Counter(
    "bayesian_prior_updates_total",
    "Total number of prior mean updates from system average",
    ["instance_id"],
    registry=registry,
)

bayesian_prior_value = Gauge(
    "bayesian_prior_value",
    "Current prior mean value (m parameter)",
    ["instance_id"],
    registry=registry,
)

bayesian_provisional_scores_total = Counter(
    "bayesian_provisional_scores_total",
    "Total number of provisional scores (rating_count < min_ratings_for_confidence)",
    ["instance_id"],
    registry=registry,
)

bayesian_no_data_scores_total = Counter(
    "bayesian_no_data_scores_total",
    "Total number of scores with zero ratings (returns prior mean)",
    ["instance_id"],
    registry=registry,
)

bayesian_rating_clamp_events_total = Counter(
    "bayesian_rating_clamp_events_total",
    "Total number of rating values clamped to valid range [0, 1]",
    ["instance_id"],
    registry=registry,
)

bayesian_scoring_duration_seconds = Histogram(
    "bayesian_scoring_duration_seconds",
    "Duration of Bayesian Average score calculation in seconds",
    ["instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

bayesian_fallback_activations_total = Counter(
    "bayesian_fallback_activations_total",
    "Total number of fallback activations due to errors (returns prior mean)",
    ["error_type", "instance_id"],
    registry=registry,
)

nats_events_published_total = Counter(
    "nats_events_published_total",
    "Total NATS events published",
    ["event_type", "stream", "instance_id"],
    registry=registry,
)

nats_duplicate_events_total = Counter(
    "nats_duplicate_events_total",
    "Total duplicate NATS events detected by JetStream",
    ["event_type", "stream", "instance_id"],
    registry=registry,
)

nats_publish_duration_seconds = Histogram(
    "nats_publish_duration_seconds",
    "Duration of NATS publish operations in seconds",
    ["event_type", "instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

nats_events_failed_total = Counter(
    "nats_events_failed_total",
    "Total NATS events that failed to publish after all retries",
    ["event_type", "error_type", "instance_id"],
    registry=registry,
)

middleware_execution_duration_seconds = Histogram(
    "middleware_execution_duration_seconds",
    "Total middleware execution time including all middleware layers",
    ["method", "endpoint", "instance_id"],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

cors_preflight_requests_total = Counter(
    "cors_preflight_requests_total",
    "Total CORS preflight OPTIONS requests received",
    ["origin", "path", "instance_id"],
    registry=registry,
)

encryption_key_age_days = Gauge(
    "encryption_key_age_days",
    "Age of encryption key in days by configuration",
    ["config_id", "instance_id"],
    registry=registry,
)

encryption_key_rotations_total = Counter(
    "encryption_key_rotations_total",
    "Total number of encryption key rotations",
    ["config_id", "reason", "instance_id"],
    registry=registry,
)

encryption_key_age_alerts_total = Counter(
    "encryption_key_age_alerts_total",
    "Total number of encryption key age alerts triggered",
    ["config_id", "instance_id"],
    registry=registry,
)

encryption_keys_needing_rotation = Gauge(
    "encryption_keys_needing_rotation",
    "Number of encryption keys that are due for rotation",
    ["instance_id"],
    registry=registry,
)

ai_notes_generated_total = Counter(
    "ai_notes_generated_total",
    "Total number of AI-generated notes",
    ["community_server_id", "dataset_name", "instance_id"],
    registry=registry,
)

ai_notes_failed_total = Counter(
    "ai_notes_failed_total",
    "Total number of failed AI note generation attempts",
    ["community_server_id", "error_type", "instance_id"],
    registry=registry,
)

ai_note_generation_duration_seconds = Histogram(
    "ai_note_generation_duration_seconds",
    "Duration of AI note generation in seconds",
    ["community_server_id", "instance_id"],
    registry=registry,
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

bulk_scan_finalization_dispatch_total = Counter(
    "bulk_scan_finalization_dispatch_total",
    "Total bulk scan finalization dispatch attempts by outcome",
    ["outcome", "instance_id"],
    registry=registry,
)

relevance_check_total = Counter(
    "relevance_check_total",
    "Total LLM relevance check outcomes",
    ["outcome", "decision", "instance_id"],
    registry=registry,
)

search_analytics_failures_total = Counter(
    "search_analytics_failures_total",
    "Total failures when logging search analytics to Redis",
    ["operation", "instance_id"],
    registry=registry,
)

semaphore_release_failures_total = Counter(
    "semaphore_release_failures_total",
    "Total semaphore release failures after all retries exhausted",
    ["task_name", "instance_id"],
    registry=registry,
)

semaphore_release_retries_total = Counter(
    "semaphore_release_retries_total",
    "Total semaphore release retry attempts",
    ["task_name", "instance_id"],
    registry=registry,
)

semaphore_leak_prevented_total = Counter(
    "semaphore_leak_prevented_total",
    "Total semaphore leaks prevented by checking existing task_id tracking",
    ["task_name", "instance_id"],
    registry=registry,
)

batch_job_stuck_count = Gauge(
    "batch_job_stuck_count",
    "Number of batch jobs stuck in non-terminal state with zero progress",
    ["job_type", "instance_id"],
    registry=registry,
)

batch_job_stuck_duration_seconds = Gauge(
    "batch_job_stuck_duration_seconds",
    "Duration in seconds that batch jobs have been stuck (max across stuck jobs)",
    ["job_type", "instance_id"],
    registry=registry,
)

batch_job_stale_cleanup_total = Counter(
    "batch_job_stale_cleanup_total",
    "Total number of stale batch jobs cleaned up by scheduled task",
    ["job_type", "instance_id"],
    registry=registry,
)


def get_metrics() -> bytes:
    return generate_latest(registry)
