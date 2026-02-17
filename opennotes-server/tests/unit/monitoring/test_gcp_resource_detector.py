"""Unit tests for GCP Cloud Run resource detection."""

from unittest.mock import MagicMock, patch
from urllib.error import URLError

from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

from src.monitoring.gcp_resource_detector import (
    _get_instance_id,
    _get_instance_id_from_metadata,
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

    def test_faas_instance_falls_back_to_revision_when_no_instance_id(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "K_REVISION": "test-service-00001-xyz",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
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

    def test_full_cloud_run_environment_with_instance_id(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
            "K_REVISION": "opennotes-server-00042-def",
            "GOOGLE_CLOUD_PROJECT": "open-notes-core",
            "CLOUD_RUN_REGION": "us-central1",
            "INSTANCE_ID": "00bf4bf02d54b1c89a80e2ca7a51b29a0979dee76f77",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)

            assert attrs[ResourceAttributes.CLOUD_PROVIDER] == "gcp"
            assert attrs[ResourceAttributes.CLOUD_PLATFORM] == "gcp_cloud_run"
            assert attrs[ResourceAttributes.CLOUD_ACCOUNT_ID] == "open-notes-core"
            assert attrs[ResourceAttributes.CLOUD_REGION] == "us-central1"
            assert attrs[ResourceAttributes.FAAS_NAME] == "opennotes-server"
            assert attrs[ResourceAttributes.FAAS_VERSION] == "opennotes-server-00042-def"
            assert (
                attrs[ResourceAttributes.FAAS_INSTANCE]
                == "00bf4bf02d54b1c89a80e2ca7a51b29a0979dee76f77"
            )
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


class TestGetInstanceIdFromMetadata:
    def test_returns_instance_id_from_metadata_server(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"00bf4bf02d54b1c89a80e2ca7a51b29a0979dee76f77"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = _get_instance_id_from_metadata()
            assert result == "00bf4bf02d54b1c89a80e2ca7a51b29a0979dee76f77"

            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert request.full_url.endswith("/instance/id")
            assert request.headers.get("Metadata-flavor") == "Google"

    def test_strips_whitespace_from_response(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"  instance-123  \n"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _get_instance_id_from_metadata()
            assert result == "instance-123"

    def test_returns_none_on_url_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            result = _get_instance_id_from_metadata()
            assert result is None

    def test_returns_none_on_timeout(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("Timed out")):
            result = _get_instance_id_from_metadata()
            assert result is None

    def test_returns_none_on_os_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("Network unreachable")):
            result = _get_instance_id_from_metadata()
            assert result is None


class TestGetInstanceId:
    def test_prefers_instance_id_env_var(self) -> None:
        env = {"INSTANCE_ID": "env-instance-id"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata"
            ) as mock_metadata,
        ):
            result = _get_instance_id(fallback="revision-123")
            assert result == "env-instance-id"
            mock_metadata.assert_not_called()

    def test_uses_metadata_when_env_not_set(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value="metadata-instance-id",
            ),
        ):
            result = _get_instance_id(fallback="revision-123")
            assert result == "metadata-instance-id"

    def test_uses_fallback_when_both_unavailable(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = _get_instance_id(fallback="revision-123")
            assert result == "revision-123"

    def test_returns_none_when_all_sources_unavailable(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = _get_instance_id(fallback=None)
            assert result is None


class TestFaasInstancePriority:
    def test_instance_id_env_takes_priority_over_revision(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "K_REVISION": "test-service-00001-xyz",
            "INSTANCE_ID": "env-instance-abc123",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.FAAS_INSTANCE] == "env-instance-abc123"
            assert attrs[ResourceAttributes.FAAS_VERSION] == "test-service-00001-xyz"

    def test_metadata_instance_id_takes_priority_over_revision(self) -> None:
        env = {
            "K_SERVICE": "test-service",
            "K_REVISION": "test-service-00001-xyz",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value="metadata-instance-def456",
            ),
        ):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs[ResourceAttributes.FAAS_INSTANCE] == "metadata-instance-def456"
            assert attrs[ResourceAttributes.FAAS_VERSION] == "test-service-00001-xyz"


class TestAppHubAttributes:
    def test_apphub_attributes_added_when_env_vars_set(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
            "GCP_APPHUB_APPLICATION": "open-notes-amethyst",
            "GCP_APPHUB_SERVICE": "opennotes-server",
            "GCP_APPHUB_CRITICALITY": "HIGH",
            "GCP_APPHUB_ENVIRONMENT_TYPE": "PRODUCTION",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs["gcp.apphub.application"] == "open-notes-amethyst"
            assert attrs["gcp.apphub.service"] == "opennotes-server"
            assert attrs["gcp.apphub.criticality"] == "HIGH"
            assert attrs["gcp.apphub.environment"] == "PRODUCTION"

    def test_apphub_attributes_omitted_when_not_set(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert "gcp.apphub.application" not in attrs
            assert "gcp.apphub.service" not in attrs
            assert "gcp.apphub.criticality" not in attrs
            assert "gcp.apphub.environment" not in attrs

    def test_apphub_service_defaults_to_k_service(self) -> None:
        env = {
            "K_SERVICE": "opennotes-server",
            "GCP_APPHUB_APPLICATION": "open-notes-amethyst",
        }
        with patch.dict("os.environ", env, clear=True):
            result = detect_gcp_cloud_run_resource()
            assert result is not None
            attrs = dict(result.attributes)
            assert attrs["gcp.apphub.application"] == "open-notes-amethyst"
            assert attrs["gcp.apphub.service"] == "opennotes-server"
