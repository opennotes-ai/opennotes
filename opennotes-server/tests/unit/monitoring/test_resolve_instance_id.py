from unittest.mock import patch

from src.monitoring.gcp_resource_detector import resolve_effective_instance_id


class TestResolveEffectiveInstanceId:
    def test_non_cloud_run_returns_config_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_effective_instance_id("opennotes-server-1")
        assert result == "opennotes-server-1"

    def test_cloud_run_uses_metadata_server(self) -> None:
        with (
            patch.dict("os.environ", {"K_SERVICE": "opennotes-server"}, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value="00bf4bf02dca965ec42fa920c038aee3ba0e182af2640f5e38a44cd1586a77e869d82be4506a3e3a2d0754b2e27cf0c9fcf32",
            ),
        ):
            result = resolve_effective_instance_id("opennotes-server-1")
        assert (
            result
            == "00bf4bf02dca965ec42fa920c038aee3ba0e182af2640f5e38a44cd1586a77e869d82be4506a3e3a2d0754b2e27cf0c9fcf32"
        )

    def test_cloud_run_falls_back_to_config_when_metadata_unavailable(self) -> None:
        with (
            patch.dict("os.environ", {"K_SERVICE": "opennotes-server"}, clear=True),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = resolve_effective_instance_id("opennotes-server-1")
        assert result == "opennotes-server-1"

    def test_cloud_run_ignores_static_instance_id_env_var(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "opennotes-dbos-worker", "INSTANCE_ID": "opennotes-dbos-worker-1"},
                clear=True,
            ),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value="unique-container-abc123",
            ),
        ):
            result = resolve_effective_instance_id("opennotes-dbos-worker-1")
        assert result == "unique-container-abc123"

    def test_dbos_worker_falls_back_to_config_when_metadata_unavailable(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {"K_SERVICE": "opennotes-dbos-worker", "INSTANCE_ID": "opennotes-dbos-worker-1"},
                clear=True,
            ),
            patch(
                "src.monitoring.gcp_resource_detector._get_instance_id_from_metadata",
                return_value=None,
            ),
        ):
            result = resolve_effective_instance_id("opennotes-dbos-worker-1")
        assert result == "opennotes-dbos-worker-1"
