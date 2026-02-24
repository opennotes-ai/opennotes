import logging

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from src.monitoring.instance import InstanceMetadata, initialize_instance_metadata
from src.monitoring.logging import CustomJsonFormatter


class TestInstanceMetadata:
    def test_initialize_instance_metadata(self) -> None:
        metadata = initialize_instance_metadata(instance_id="test-instance-1", environment="test")

        assert metadata.instance_id == "test-instance-1"
        assert metadata.environment == "test"
        assert metadata.hostname is not None
        assert metadata.pod_name is not None

    def test_instance_metadata_to_dict(self) -> None:
        metadata = initialize_instance_metadata(instance_id="test-instance-1", environment="test")

        metadata_dict = metadata.to_dict()
        assert metadata_dict["instance_id"] == "test-instance-1"
        assert metadata_dict["environment"] == "test"
        assert "hostname" in metadata_dict
        assert "pod_name" in metadata_dict

    def test_get_instance(self) -> None:
        initialize_instance_metadata(instance_id="test-instance-2", environment="staging")

        retrieved = InstanceMetadata.get_instance()
        assert retrieved is not None
        assert retrieved.instance_id == "test-instance-2"

    def test_instance_id_classmethod(self) -> None:
        initialize_instance_metadata(instance_id="test-instance-3", environment="production")

        assert InstanceMetadata.instance_id() == "test-instance-3"

    def test_hostname_classmethod(self) -> None:
        initialize_instance_metadata(instance_id="test-instance-4", environment="test")

        hostname = InstanceMetadata.hostname()
        assert hostname is not None
        assert len(hostname) > 0

    def test_get_instance_without_initialization(self) -> None:
        InstanceMetadata._instance = None

        assert InstanceMetadata.get_instance() is None
        assert InstanceMetadata.instance_id() == "unknown"

    def test_instance_id_in_logs(self) -> None:
        initialize_instance_metadata(instance_id="logging-test-instance", environment="test")

        logging.getLogger(__name__)
        formatter = CustomJsonFormatter("%(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        log_dict = {}
        formatter.add_fields(log_dict, record, {})

        assert log_dict.get("instance_id") == "logging-test-instance"
        assert "hostname" in log_dict

    def test_otel_metrics_recorded(self) -> None:
        initialize_instance_metadata(instance_id="metrics-test-instance", environment="test")

        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        meter = provider.get_meter("test-instance-metadata")
        counter = meter.create_counter("test.http.requests")
        histogram = meter.create_histogram("test.http.duration")

        counter.add(1, {"method": "GET", "endpoint": "/test", "status": "200"})
        histogram.record(0.5, {"method": "GET", "endpoint": "/test"})

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        resource_metrics = metrics_data.resource_metrics
        assert len(resource_metrics) > 0
