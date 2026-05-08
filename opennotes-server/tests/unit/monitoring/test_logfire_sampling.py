from types import SimpleNamespace

from src.monitoring.logfire_sampling import build_logfire_tail_sampler


def make_span_info(
    *,
    name: str = "worker span",
    scope: str = "worker",
    attributes: dict[str, str] | None = None,
    level: str = "info",
    duration: float = 0.1,
) -> SimpleNamespace:
    span = SimpleNamespace(
        name=name,
        instrumentation_scope=SimpleNamespace(name=scope),
        attributes=attributes or {},
    )
    return SimpleNamespace(span=span, level=level, duration=duration)


def test_worker_redis_span_uses_dbos_datastore_sample_rate() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.007,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(scope="opentelemetry.instrumentation.redis"))

    assert rate == 0.007


def test_worker_postgres_span_clamps_dbos_datastore_sample_rate() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.5,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(attributes={"db.system": "postgresql"}))

    assert rate == 0.01


def test_worker_sqlalchemy_span_defaults_to_full_suppression() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.0,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(scope="opentelemetry.instrumentation.sqlalchemy"))

    assert rate == 0.0


def test_worker_dbos_internal_span_uses_dbos_datastore_sample_rate() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.005,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(name="DBOS enqueue workflow", scope="dbos"))

    assert rate == 0.005


def test_warning_worker_datastore_span_passes_to_logfire() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.0,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(attributes={"db.system": "redis"}, level="warning"))

    assert rate == 1.0


def test_slow_worker_datastore_span_passes_to_logfire() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.0,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(attributes={"db.system": "postgresql"}, duration=6.0))

    assert rate == 1.0


def test_genai_span_keeps_elevated_sample_rate() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-dbos-worker",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.0,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(name="openai chat completion"))

    assert rate == 0.2


def test_non_worker_datastore_span_uses_background_sample_rate() -> None:
    sampler = build_logfire_tail_sampler(
        service_name="opennotes-server",
        background_sample_rate=0.4,
        dbos_datastore_sample_rate=0.0,
        tail_level_threshold="warning",
        tail_duration_threshold=5.0,
    )

    rate = sampler(make_span_info(attributes={"db.system": "postgresql"}))

    assert rate == 0.4
