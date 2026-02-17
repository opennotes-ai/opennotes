"""
Audit logging helper functions for user management operations.

This module provides utilities for creating audit log entries for sensitive
operations in the users system, including authentication, profile changes,
identity management, and API key operations.
"""

from typing import Any
from uuid import UUID

import orjson
import pendulum
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import AuditLog


async def create_audit_log(
    db: AsyncSession,
    user_id: UUID | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """
    Create an audit log entry for a sensitive operation.

    Args:
        db: Database session
        user_id: ID of the user performing the action (None for unauthenticated actions)
        action: Action being performed (e.g., "CREATE_USER", "UPDATE_PASSWORD")
        resource: Resource type (e.g., "user", "api_key", "identity")
        resource_id: Identifier of the affected resource (optional)
        details: Additional context about the operation (optional)
        ip_address: IP address of the request (optional)
        user_agent: User agent string of the request (optional)

    Returns:
        Created AuditLog instance
    """
    details_str = orjson.dumps(details).decode() if details else None

    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        details=details_str,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=pendulum.now("UTC"),
    )

    db.add(audit_log)
    await db.flush()

    return audit_log


def extract_request_context(request: Request) -> tuple[str | None, str | None]:
    """
    Extract IP address and user agent from a FastAPI request.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (ip_address, user_agent)
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    return ip_address, user_agent
