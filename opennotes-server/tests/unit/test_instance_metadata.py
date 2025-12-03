import logging

from src.monitoring.instance import InstanceMetadata, initialize_instance_metadata
from src.monitoring.logging import CustomJsonFormatter
from src.monitoring.metrics import (
    active_requests,
    http_request_duration_seconds,
    http_requests_total,
    registry,
)


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

    def test_metrics_with_instance_label(self) -> None:
        initialize_instance_metadata(instance_id="metrics-test-instance", environment="test")

        instance_id = "metrics-test-instance"
        http_requests_total.labels(
            method="GET", endpoint="/test", status=200, instance_id=instance_id
        ).inc()
        active_requests.labels(instance_id=instance_id).inc()
        http_request_duration_seconds.labels(
            method="GET", endpoint="/test", instance_id=instance_id
        ).observe(0.5)

        metrics_output = registry.collect()
        metrics_list = list(metrics_output)

        assert len(metrics_list) > 0

    def test_multiple_instances_distinguishable(self) -> None:
        instance_1_id = "instance-1"
        instance_2_id = "instance-2"

        InstanceMetadata.set_instance(
            InstanceMetadata(instance_id=instance_1_id, environment="test")
        )
        for _i in range(5):
            http_requests_total.labels(
                method="GET",
                endpoint="/test",
                status=200,
                instance_id=instance_1_id,
            ).inc()

        InstanceMetadata.set_instance(
            InstanceMetadata(instance_id=instance_2_id, environment="test")
        )
        for _i in range(3):
            http_requests_total.labels(
                method="GET",
                endpoint="/test",
                status=200,
                instance_id=instance_2_id,
            ).inc()

        from prometheus_client import generate_latest

        metrics_bytes = generate_latest(registry)
        metrics_text = metrics_bytes.decode("utf-8")

        assert f'instance_id="{instance_1_id}"' in metrics_text
        assert f'instance_id="{instance_2_id}"' in metrics_text
