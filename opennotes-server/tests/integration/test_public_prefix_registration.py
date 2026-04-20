"""Structural assertions for /api/public/v1 double-registration (TASK-1461.02).

Verifies that every PublicRouterSpec in PUBLIC_ADAPTER_ROUTERS is mounted under
its legacy prefix and API_PUBLIC_V1_PREFIX, that non-allowlisted routers and
explicitly filtered-out paths are NOT double-registered, and that public routes
carry the "public" OpenAPI tag.

Pure route-table inspection — no HTTP or database traffic.
"""

from starlette.routing import Route

from src.config import settings
from src.main import app
from src.public_api import API_PUBLIC_V1_PREFIX, PUBLIC_ADAPTER_ROUTERS


def _router_path_suffixes(router, allowlist: frozenset[str] | None) -> set[str]:
    suffixes = {route.path for route in router.routes if isinstance(route, Route)}
    if allowlist is not None:
        suffixes &= allowlist
    return suffixes


def _app_paths_with_prefix(prefix: str) -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, Route) and route.path.startswith(prefix)
    }


def test_each_allowlisted_router_has_paths_under_both_prefixes():
    v2_prefix = settings.API_V2_PREFIX
    public_prefix = API_PUBLIC_V1_PREFIX
    assert public_prefix == "/api/public/v1"

    for spec in PUBLIC_ADAPTER_ROUTERS:
        suffixes = _router_path_suffixes(spec.router, spec.path_allowlist)
        assert suffixes, f"Router spec {spec} has no routes to mount"
        for suffix in suffixes:
            legacy_path = f"{v2_prefix}{suffix}"
            public_path = f"{public_prefix}{suffix}"
            app_legacy = any(isinstance(r, Route) and r.path == legacy_path for r in app.routes)
            app_public = any(isinstance(r, Route) and r.path == public_path for r in app.routes)
            assert app_legacy, f"Missing legacy registration: {legacy_path}"
            assert app_public, f"Missing public registration: {public_path}"


def test_allowlist_filters_non_public_profile_paths_off_the_public_surface():
    """/profiles/me and /profiles/{id}/opennotes-admin must stay on /api/v2 only."""
    public_paths = _app_paths_with_prefix(API_PUBLIC_V1_PREFIX)
    forbidden_tokens = (
        "/profiles/me",
        "/profiles/{profile_id}",  # covers both the read and opennotes-admin patch
    )
    for token in forbidden_tokens:
        offenders = [p for p in public_paths if token in p]
        assert not offenders, (
            f"Filtered profile path '{token}' leaked to the public surface: {offenders}"
        )


def test_public_prefix_does_not_register_non_allowlisted_routes():
    public_paths = _app_paths_with_prefix(API_PUBLIC_V1_PREFIX)
    # bulk-scans is deliberately deferred from the allowlist — see task plan
    assert all("/bulk-scans" not in p for p in public_paths), (
        f"bulk-scans must not be on the public surface: {sorted(public_paths)}"
    )
    # Simulation/playground/admin routes must not be public either.
    for token in ("/simulations", "/playground", "/sim-agents", "/orchestrators", "/admin"):
        offenders = [p for p in public_paths if token in p]
        assert not offenders, f"Non-adapter routes leaked to public: {offenders}"


def test_public_routes_carry_public_openapi_tag():
    schema = app.openapi()
    public_ops = [
        op
        for path, path_item in schema.get("paths", {}).items()
        if path.startswith(API_PUBLIC_V1_PREFIX)
        for op in path_item.values()
        if isinstance(op, dict)
    ]
    assert public_ops, "Expected at least one public operation in OpenAPI schema"
    for op in public_ops:
        tags = op.get("tags", [])
        assert "public" in tags, f"Public operation missing 'public' tag: {op.get('operationId')}"


def test_openapi_contains_both_prefix_variants_for_allowlist():
    schema = app.openapi()
    paths = set(schema.get("paths", {}).keys())
    v2_prefix = settings.API_V2_PREFIX

    for spec in PUBLIC_ADAPTER_ROUTERS:
        for suffix in _router_path_suffixes(spec.router, spec.path_allowlist):
            legacy = f"{v2_prefix}{suffix}"
            public = f"{API_PUBLIC_V1_PREFIX}{suffix}"
            assert legacy in paths, f"Legacy not in OpenAPI: {legacy}"
            assert public in paths, f"Public not in OpenAPI: {public}"
