"""GCP Cloud Run resource detector for OpenTelemetry.

Detects Cloud Run environment and provides semantic convention attributes
for cloud provider and FaaS resources.

Environment Variables:
    - K_SERVICE: Cloud Run service name (also triggers detection)
    - K_REVISION: Cloud Run revision name
    - GOOGLE_CLOUD_PROJECT: GCP project ID
    - CLOUD_RUN_REGION: Cloud Run region (may also be CLOUD_RUN_LOCATION)

References:
    - https://opentelemetry.io/docs/specs/semconv/resource/cloud-provider/gcp/
    - https://opentelemetry.io/docs/specs/semconv/resource/faas/

Created: task-1064.03
"""

from __future__ import annotations

import logging
import os
import urllib.request
from typing import TYPE_CHECKING
from urllib.error import URLError

if TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

METADATA_SERVER_URL = "http://metadata.google.internal/computeMetadata/v1"
METADATA_INSTANCE_ID_PATH = "/instance/id"
METADATA_TIMEOUT_SECONDS = 2.0


def _get_instance_id_from_metadata() -> str | None:
    """Fetch Cloud Run instance ID from GCP metadata server.

    Returns:
        Instance ID string, or None if unavailable.
    """
    url = f"{METADATA_SERVER_URL}{METADATA_INSTANCE_ID_PATH}"
    request = urllib.request.Request(
        url,
        headers={"Metadata-Flavor": "Google"},
    )

    try:
        with urllib.request.urlopen(request, timeout=METADATA_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8").strip()
    except (URLError, TimeoutError, OSError) as e:
        logger.debug(f"Could not fetch instance ID from metadata server: {e}")
        return None


def _get_instance_id(fallback: str | None = None) -> str | None:
    """Get Cloud Run instance ID from environment or metadata server.

    Priority:
        1. INSTANCE_ID environment variable (if set)
        2. GCP metadata server
        3. Fallback value (typically K_REVISION)

    Args:
        fallback: Value to return if instance ID unavailable from other sources.

    Returns:
        Instance ID string, or fallback if unavailable.
    """
    instance_id = os.getenv("INSTANCE_ID")
    if instance_id:
        return instance_id

    instance_id = _get_instance_id_from_metadata()
    if instance_id:
        return instance_id

    return fallback


def resolve_effective_instance_id(config_default: str) -> str:
    """Resolve a unique instance ID, preferring GCP metadata server in Cloud Run.

    In Cloud Run, multiple instances share the same INSTANCE_ID env var
    (service-level config). The metadata server returns a unique ID per
    container, which is required for Cloud Monitoring metrics identity.

    Priority in Cloud Run:
        1. GCP metadata server (unique per container)
        2. config_default (static fallback)

    Outside Cloud Run:
        Returns config_default unchanged.

    Args:
        config_default: The settings.INSTANCE_ID value to use as fallback.

    Returns:
        A unique instance ID string.
    """
    if not is_cloud_run_environment():
        return config_default

    metadata_id = _get_instance_id_from_metadata()
    if metadata_id:
        logger.info(f"Resolved unique instance ID from metadata server: {metadata_id}")
        return metadata_id

    logger.warning(
        f"Could not resolve instance ID from metadata server, "
        f"falling back to config default: {config_default}"
    )
    return config_default


def is_cloud_run_environment() -> bool:
    """Check if running in Cloud Run environment.

    Detection is based on K_SERVICE environment variable which is always
    set in Cloud Run.

    Returns:
        True if running in Cloud Run, False otherwise.
    """
    return bool(os.getenv("K_SERVICE"))


def detect_gcp_cloud_run_resource() -> Resource | None:
    """Detect GCP Cloud Run environment and return Resource with attributes.

    Returns Resource with GCP cloud and FaaS semantic convention attributes
    if running in Cloud Run, otherwise returns None.

    Attributes set:
        - cloud.provider: "gcp"
        - cloud.platform: "gcp_cloud_run"
        - cloud.account.id: GCP project ID
        - cloud.region: Cloud Run region
        - cloud.resource_id: Full Cloud Run resource path
        - faas.name: Service name
        - faas.version: Revision name
        - faas.instance: Instance ID (from env/metadata) or revision as fallback

    Returns:
        Resource with GCP attributes, or None if not in Cloud Run.
    """
    if not is_cloud_run_environment():
        return None

    try:
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.semconv.resource import ResourceAttributes  # noqa: PLC0415

        service_name = os.getenv("K_SERVICE", "")
        revision = os.getenv("K_REVISION", "")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        region = os.getenv("CLOUD_RUN_REGION") or os.getenv("CLOUD_RUN_LOCATION", "")

        attributes: dict[str, str] = {
            ResourceAttributes.CLOUD_PROVIDER: "gcp",
            ResourceAttributes.CLOUD_PLATFORM: "gcp_cloud_run",
        }

        if service_name:
            attributes[ResourceAttributes.FAAS_NAME] = service_name

        if revision:
            attributes[ResourceAttributes.FAAS_VERSION] = revision

        instance_id = _get_instance_id(fallback=revision)
        if instance_id:
            attributes[ResourceAttributes.FAAS_INSTANCE] = instance_id

        if project_id:
            attributes[ResourceAttributes.CLOUD_ACCOUNT_ID] = project_id

        if region:
            attributes[ResourceAttributes.CLOUD_REGION] = region

        if project_id and region and service_name:
            resource_id = (
                f"//run.googleapis.com/projects/{project_id}"
                f"/locations/{region}/services/{service_name}"
            )
            attributes[ResourceAttributes.CLOUD_RESOURCE_ID] = resource_id

        logger.info(
            f"GCP Cloud Run resource detected: service={service_name}, "
            f"revision={revision}, region={region}"
        )

        return Resource(attributes)

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to detect GCP Cloud Run resource: {e}")
        return None
