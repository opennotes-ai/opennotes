"""
Schemathesis property-based API tests.

Auto-generates test cases from the OpenAPI schema to catch:
- Unexpected 5xx errors for valid inputs
- Response schema violations
- Edge cases missed by hand-written tests

Uses ASGI integration (no HTTP overhead) with Schemathesis.

Requires test services (postgres, redis, nats) to be available.
Run via: mise run test:schemathesis
"""

import os

import schemathesis
from hypothesis import HealthCheck, Verbosity
from hypothesis import settings as hypothesis_settings

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DEBUG", "true")

hypothesis_settings.register_profile(
    "dev",
    max_examples=50,
    verbosity=Verbosity.verbose,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
hypothesis_settings.register_profile(
    "ci",
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
hypothesis_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

from src.main import app  # noqa: E402

schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", app=app)


@schemathesis.check
def no_sensitive_data_in_errors(ctx, response, case):
    """Error responses should not leak sensitive information."""
    if response.status_code >= 400:
        body = response.text.lower()
        sensitive_patterns = ["traceback", "stack trace", "sqlalchemy", "asyncpg", "password"]
        for pattern in sensitive_patterns:
            if pattern in body:
                raise AssertionError(
                    f"Sensitive pattern '{pattern}' found in {response.status_code} response "
                    f"for {case.method} {case.path}"
                )


@schema.parametrize()
@hypothesis_settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_api_no_server_errors(case):
    """No endpoint should return 5xx for any generated input."""
    response = case.call()
    assert response.status_code < 500, f"{case.method} {case.path} returned {response.status_code}"


@schema.parametrize()
@hypothesis_settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_api_schema_conformance(case):
    """All responses should conform to their declared OpenAPI schemas."""
    case.call_and_validate()
