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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)


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
        - faas.instance: Revision name (execution environment ID)

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
            attributes[ResourceAttributes.FAAS_INSTANCE] = revision

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
