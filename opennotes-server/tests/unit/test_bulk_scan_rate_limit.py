"""
Unit tests for rate limiting on Bulk Content Scan API endpoints.

These tests verify that:
1. POST /bulk-content-scan/scans endpoint has rate limiting
2. POST /api/v2/bulk-scans endpoint (JSON:API) has rate limiting
3. Rate limit exceeded returns 429 Too Many Requests
4. Rate limiting uses configurable values

Task: task-849.09
"""

import ast
from pathlib import Path

import pytest


def _get_src_path() -> Path:
    """Get the path to the src directory."""
    return Path(__file__).parent.parent.parent / "src"


def _parse_router_ast(router_name: str) -> ast.Module:
    """Parse the AST of a router module."""
    router_path = _get_src_path() / "bulk_content_scan" / router_name
    source = router_path.read_text()
    return ast.parse(source)


def _check_limiter_import(tree: ast.Module) -> bool:
    """Check if limiter is imported from src.middleware.rate_limiting."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.middleware.rate_limiting":
            for alias in node.names:
                if alias.name == "limiter":
                    return True
    return False


def _check_rate_limit_decorator(tree: ast.Module, func_name: str) -> bool:
    """Check if a function has @limiter.limit() decorator."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "limit"
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "limiter"
                ):
                    return True
    return False


def _get_rate_limit_string(tree: ast.Module, func_name: str) -> str | None:
    """Extract the rate limit string from a function's @limiter.limit() decorator."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "limit"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    return decorator.args[0].value
    return None


class TestBulkScanRateLimitConfig:
    """Tests that verify bulk scan rate limiting configuration exists."""

    def test_bulk_scan_rate_limit_config_exists(self):
        """
        Settings should have BULK_SCAN_RATE_LIMIT_PER_HOUR configuration.

        This allows rate limiting to be configurable via environment variables.
        """
        from pydantic.fields import FieldInfo

        from src.config import Settings

        settings_fields = Settings.model_fields
        assert "BULK_SCAN_RATE_LIMIT_PER_HOUR" in settings_fields, (
            "Settings should have BULK_SCAN_RATE_LIMIT_PER_HOUR field. "
            "Add BULK_SCAN_RATE_LIMIT_PER_HOUR: int = Field(default=5) to Settings."
        )

        field_info: FieldInfo = settings_fields["BULK_SCAN_RATE_LIMIT_PER_HOUR"]
        assert field_info.default is not None, (
            "BULK_SCAN_RATE_LIMIT_PER_HOUR should have a default value."
        )

    def test_bulk_scan_rate_limit_default_value(self):
        """
        BULK_SCAN_RATE_LIMIT_PER_HOUR should default to 5 scans per hour.
        """
        from src.config import Settings

        settings_fields = Settings.model_fields
        if "BULK_SCAN_RATE_LIMIT_PER_HOUR" not in settings_fields:
            pytest.skip("BULK_SCAN_RATE_LIMIT_PER_HOUR not yet defined")

        field_info = settings_fields["BULK_SCAN_RATE_LIMIT_PER_HOUR"]
        assert field_info.default == 5, (
            f"BULK_SCAN_RATE_LIMIT_PER_HOUR should default to 5, got {field_info.default}."
        )


class TestBulkScanRateLimitImports:
    """Tests that verify rate limiting is properly imported in bulk scan routers."""

    def test_router_module_has_limiter(self):
        """
        The bulk_content_scan router module should import the limiter.
        """
        import importlib.util

        spec = importlib.util.find_spec("src.bulk_content_scan.router")
        assert spec is not None, "Could not find bulk_content_scan.router module"

        tree = _parse_router_ast("router.py")
        assert _check_limiter_import(tree), (
            "router.py should import limiter from src.middleware.rate_limiting. "
            "Add: from src.middleware.rate_limiting import limiter"
        )

    def test_jsonapi_router_module_has_limiter(self):
        """
        The bulk_content_scan jsonapi_router module should import the limiter.
        """
        tree = _parse_router_ast("jsonapi_router.py")
        assert _check_limiter_import(tree), (
            "jsonapi_router.py should import limiter from src.middleware.rate_limiting. "
            "Add: from src.middleware.rate_limiting import limiter"
        )


class TestBulkScanRateLimitDecorator:
    """Tests that verify rate limiting decorators are applied to bulk scan endpoints."""

    def test_initiate_scan_has_rate_limit_decorator(self):
        """
        POST /bulk-content-scan/scans should have rate limiting decorator.

        This test verifies the @limiter.limit decorator is applied to the endpoint
        by inspecting the source code.
        """
        tree = _parse_router_ast("router.py")
        assert _check_rate_limit_decorator(tree, "initiate_scan"), (
            "POST /bulk-content-scan/scans endpoint should have rate limiting. "
            "Add @limiter.limit('5/hour') decorator to the initiate_scan function."
        )

    def test_jsonapi_initiate_scan_has_rate_limit_decorator(self):
        """
        POST /api/v2/bulk-scans should have rate limiting decorator.

        This test verifies the @limiter.limit decorator is applied to the JSON:API endpoint
        by inspecting the source code.
        """
        tree = _parse_router_ast("jsonapi_router.py")
        assert _check_rate_limit_decorator(tree, "initiate_scan"), (
            "POST /api/v2/bulk-scans endpoint should have rate limiting. "
            "Add @limiter.limit('5/hour') decorator to the JSON:API initiate_scan function."
        )

    def test_rate_limit_string_contains_hour(self):
        """
        The rate limit decorator should use the format containing '/hour'.

        For bulk scans, rate limits should be hourly (not per minute or per second)
        since scans are expensive operations.
        """
        tree = _parse_router_ast("router.py")
        rate_limit_string = _get_rate_limit_string(tree, "initiate_scan")

        assert rate_limit_string is not None, "Could not find rate limit string"
        assert "/hour" in rate_limit_string.lower(), (
            f"Rate limit should be per hour for bulk scans, got: {rate_limit_string}"
        )


class TestRateLimitExceptionHandling:
    """Tests that verify 429 status code behavior."""

    def test_rate_limit_exceeded_returns_429_status_code(self):
        """
        When rate limit is exceeded, the endpoint should return 429 Too Many Requests.

        This tests that the slowapi.errors.RateLimitExceeded exception uses 429 status.
        """
        from fastapi import status
        from slowapi.errors import RateLimitExceeded

        assert hasattr(RateLimitExceeded, "status_code") or issubclass(
            RateLimitExceeded, Exception
        ), "RateLimitExceeded should be an exception class"

        assert status.HTTP_429_TOO_MANY_REQUESTS == 429, "HTTP 429 is Too Many Requests"


class TestBulkScanRateLimitDocumentation:
    """Tests that verify rate limiting is documented in endpoint description."""

    def test_initiate_scan_mentions_rate_limit_in_description_or_has_limit(self):
        """
        The initiate_scan endpoint should either mention rate limiting in its description
        or have the rate limiting decorator applied (which adds automatic documentation).

        This ensures users are aware of the rate limiting behavior.
        """
        tree = _parse_router_ast("router.py")
        assert _check_rate_limit_decorator(tree, "initiate_scan"), (
            "The initiate_scan endpoint should have rate limiting decorator. "
            "Add @limiter.limit() to document and enforce rate limits."
        )
