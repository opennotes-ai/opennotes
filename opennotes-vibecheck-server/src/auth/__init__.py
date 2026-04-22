"""Authentication helpers for the internal worker endpoint.

`cloud_tasks_oidc` implements the OIDC-token verification that gates
`POST /_internal/jobs/{job_id}/run` against untrusted callers. Only
tokens signed by Google (issuer `https://accounts.google.com`) with
audience matching `VIBECHECK_SERVER_URL` and email matching
`VIBECHECK_TASKS_ENQUEUER_SA` are accepted; everything else returns 401.
"""
from __future__ import annotations

from src.auth.cloud_tasks_oidc import verify_cloud_tasks_oidc

__all__ = ["verify_cloud_tasks_oidc"]
