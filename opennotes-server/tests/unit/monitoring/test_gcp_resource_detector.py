"""Unit tests for GCP Cloud Run resource detection."""

from unittest.mock import patch

from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

from src.monitoring.gcp_resource_detector import (
    detect_gcp_cloud_run_resource,
    is_cloud_run_environment,
)


class TestIsCloudRunEnvironment:
    def test_returns_true_when_k_service_set(self) -> None:
        with patch.dict("os.environ", {"K_SERVICE": "my-service"}, clear=False):
            assert is_cloud_run_environment() is True

    def test_returns_false_when_k_service_not_set(self) -> None:
        env = {"SOME_OTHER_VAR": "value"}
        with patch.dict("os.environ", env, clear=True):
            assert is_cloud_run_environment() is False

    def test_returns_false_when_k_service_empty(self) -> None:
        with patch.dict("os.environ", {"K_SERVICE": ""}, clear=False):
            assert is_cloud_run_environment() is False


class TestDetectGcpCloudRunResource:
    def test_returns_none_outside_cloud_run(self) -> None:
        env: dict[str, str] = {}
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is None

    def test_includes_cloud_provider_gcp(self) -> None:
        env = {"K_SERVICE": "test-service"}
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_PROVIDER] == "gcp"

    def test_includes_cloud_platform_gcp_cloud_run(self) -> None:
        env = {"K_SERVICE": "test-service"}
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_PLATFORM] == "gcp_cloud_run"

    def test_includes_faas_name_from_k_service(self) -> None:
        env = {"K_SERVICE": "my-awesome-service"}
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.FAAS_NAME] == "my-awesome-service"

    def test_includes_faas_version_from_k_revision(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "K_REVISION": "test-service-00001-abc",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.FAAS_VERSION] == "test-service-00001-abc"

    def test_includes_faas_instance_from_k_revision(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "K_REVISION": "test-service-00001-xyz",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.FAAS_INSTANCE] == "test-service-00001-xyz"

    def test_includes_cloud_account_id_from_google_cloud_project(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "GOOGLE_CLOUD_PROJECT": "my-project-123",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_ACCOUNT_ID] == "my-project-123"

    def test_includes_cloud_region_from_cloud_run_region(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "CLOUD_RUN_REGION": "us-central1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_REGION] == "us-central1"

    def test_cloud_region_falls_back_to_cloud_run_location(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "CLOUD_RUN_LOCATION": "europe-west1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_REGION] == "europe-west1"

    def test_cloud_run_region_takes_precedence_over_location(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "CLOUD_RUN_REGION": "us-east1",
            "CLOUD_RUN_LOCATION": "us-west1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.CLOUD_REGION] == "us-east1"

    def test_builds_correct_cloud_resource_id_format(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
            "GOOGLE_CLOUD_PROJECT": "open-notes-core",
            "CLOUD_RUN_REGION": "us-central1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            expected = (
                "//run.googleapis.com/projects/open-notes-core"
                "/locations/us-central1/services/opennotes-server"
            )
            assert attrs[ResourceAttributes.CLOUD_RESOURCE_ID] == expected

    def test_cloud_resource_id_not_set_when_project_missing(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "CLOUD_RUN_REGION": "us-central1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert ResourceAttributes.CLOUD_RESOURCE_ID not in attrs

    def test_cloud_resource_id_not_set_when_region_missing(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "GOOGLE_CLOUD_PROJECT": "my-project",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert ResourceAttributes.CLOUD_RESOURCE_ID not in attrs

    def test_full_cloud_run_environment(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
            "K_REVISION": "opennotes-server-00042-def",
            "GOOGLE_CLOUD_PROJECT": "open-notes-core",
            "CLOUD_RUN_REGION": "us-central1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)

            assert attrs[ResourceAttributes.CLOUD_PROVIDER] == "gcp"
            assert attrs[ResourceAttributes.CLOUD_PLATFORM] == "gcp_cloud_run"
            assert attrs[ResourceAttributes.CLOUD_ACCOUNT_ID] == "open-notes-core"
            assert attrs[ResourceAttributes.CLOUD_REGION] == "us-central1"
            assert attrs[ResourceAttributes.FAAS_NAME] == "opennotes-server"
            assert attrs[ResourceAttributes.FAAS_VERSION] == "opennotes-server-00042-def"
            assert attrs[ResourceAttributes.FAAS_INSTANCE] == "opennotes-server-00042-def"
            expected_resource_id = (
                "//run.googleapis.com/projects/open-notes-core"
                "/locations/us-central1/services/opennotes-server"
            )
            assert attrs[ResourceAttributes.CLOUD_RESOURCE_ID] == expected_resource_id


class TestResourceMerge:
    def test_merge_preserves_base_attributes(self) -> None:
        base_resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: "my-service",
                ResourceAttributes.SERVICE_VERSION: "1.0.0",
            }
        )

        env = {
            "K_SERVICE": "cloud-run-service",
            "GOOGLE_CLOUD_PROJECT": "my-project",
        }
        with patch.dict("os.environ", env, clear=True):
            gcp_resource = detect_gcp_cloud_run_resource()
            assert gcp_resource is not None

            merged = base_resource.merge(gcp_resource)
            attrs = dict(merged.attributes)

            assert attrs[ResourceAttributes.SERVICE_NAME] == "my-service"
            assert attrs[ResourceAttributes.SERVICE_VERSION] == "1.0.0"

    def test_merge_adds_gcp_attributes(self) -> None:
        base_resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: "my-service",
            }
        )

        env = {
            "K_SERVICE": "cloud-run-service",
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "CLOUD_RUN_REGION": "asia-northeast1",
        }
        with patch.dict("os.environ", env, clear=True):
            gcp_resource = detect_gcp_cloud_run_resource()
            assert gcp_resource is not None

            merged = base_resource.merge(gcp_resource)
            attrs = dict(merged.attributes)

            assert attrs[ResourceAttributes.CLOUD_PROVIDER] == "gcp"
            assert attrs[ResourceAttributes.CLOUD_PLATFORM] == "gcp_cloud_run"
            assert attrs[ResourceAttributes.CLOUD_ACCOUNT_ID] == "my-project"
            assert attrs[ResourceAttributes.CLOUD_REGION] == "asia-northeast1"
            assert attrs[ResourceAttributes.FAAS_NAME] == "cloud-run-service"
