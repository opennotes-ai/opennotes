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


def _router_route_specs(
    router,
    path_allowlist: frozenset[str] | None,
    method_allowlist: frozenset[str] | None,
) -> set[tuple[str, str]]:
    specs = set()
    for route in router.routes:
        if not isinstance(route, Route):
            continue
        if path_allowlist is not None and route.path not in path_allowlist:
            continue
        methods = set(route.methods or set())
        if method_allowlist is not None:
            methods &= method_allowlist
        specs.update((route.path, method) for method in methods)
    return specs


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
        route_specs = _router_route_specs(
            spec.router,
            spec.path_allowlist,
            spec.method_allowlist,
        )
        assert route_specs, f"Router spec {spec} has no routes to mount"
        for suffix, method in route_specs:
            legacy_path = f"{v2_prefix}{suffix}"
            public_path = f"{public_prefix}{suffix}"
            app_legacy = any(
                isinstance(r, Route) and r.path == legacy_path and method in (r.methods or set())
                for r in app.routes
            )
            app_public = any(
                isinstance(r, Route) and r.path == public_path and method in (r.methods or set())
                for r in app.routes
            )
            assert app_legacy, f"Missing legacy registration: {method} {legacy_path}"
            assert app_public, f"Missing public registration: {method} {public_path}"


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
    v2_prefix = settings.API_V2_PREFIX

    for spec in PUBLIC_ADAPTER_ROUTERS:
        for suffix, method in _router_route_specs(
            spec.router,
            spec.path_allowlist,
            spec.method_allowlist,
        ):
            legacy = f"{v2_prefix}{suffix}"
            public = f"{API_PUBLIC_V1_PREFIX}{suffix}"
            assert method.lower() in schema["paths"].get(legacy, {}), (
                f"Legacy not in OpenAPI: {method} {legacy}"
            )
            assert method.lower() in schema["paths"].get(public, {}), (
                f"Public not in OpenAPI: {method} {public}"
            )


def test_public_moderation_actions_only_exposes_get_methods():
    schema = app.openapi()
    collection = schema["paths"][f"{API_PUBLIC_V1_PREFIX}/moderation-actions"]
    item = schema["paths"][f"{API_PUBLIC_V1_PREFIX}/moderation-actions/{{action_id}}"]

    assert "get" in collection
    assert "post" not in collection
    assert "get" in item
    assert "patch" not in item
