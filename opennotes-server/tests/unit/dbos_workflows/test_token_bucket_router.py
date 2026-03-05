from datetime import UTC, datetime

from src.dbos_workflows.token_bucket.schemas import TokenHoldDetail, TokenPoolStatus


class TestTokenPoolStatusSchema:
    def test_from_dict(self):
        status = TokenPoolStatus(
            pool_name="default",
            capacity=12,
            available=7,
            active_hold_count=2,
            utilization_pct=41.7,
        )
        assert status.pool_name == "default"
        assert status.capacity == 12
        assert status.available == 7
        assert status.utilization_pct == 41.7

    def test_from_attributes(self):
        class FakePool:
            pool_name = "llm"
            capacity = 10
            available = 3
            active_hold_count = 4
            utilization_pct = 70.0

        status = TokenPoolStatus.model_validate(FakePool(), from_attributes=True)
        assert status.pool_name == "llm"
        assert status.active_hold_count == 4


class TestTokenHoldDetailSchema:
    def test_from_dict(self):
        detail = TokenHoldDetail(
            workflow_id="wf-123",
            weight=5,
            acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert detail.workflow_id == "wf-123"
        assert detail.weight == 5

    def test_serialization_roundtrip(self):
        detail = TokenHoldDetail(
            workflow_id="wf-456",
            weight=3,
            acquired_at=datetime(2026, 6, 15, 12, 30, 0, tzinfo=UTC),
        )
        data = detail.model_dump()
        restored = TokenHoldDetail(**data)
        assert restored.workflow_id == detail.workflow_id
        assert restored.weight == detail.weight
        assert restored.acquired_at == detail.acquired_at


class TestTokenPoolRouterAuth:
    def test_router_has_verify_service_account_dependency(self):
        from src.dbos_workflows.token_bucket.router import router

        for route in router.routes:
            if hasattr(route, "dependant"):
                dep_names = [
                    d.call.__name__
                    for d in route.dependant.dependencies
                    if hasattr(d, "call") and hasattr(d.call, "__name__")
                ]
                assert "verify_service_account" in dep_names, (
                    f"Route {route.path} missing verify_service_account dependency"
                )

    def test_list_token_pools_requires_auth(self):
        from src.dbos_workflows.token_bucket.router import router

        list_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/admin/token-pools/":
                list_route = route
                break
        assert list_route is not None
        dep_names = [
            d.call.__name__
            for d in list_route.dependant.dependencies
            if hasattr(d, "call") and hasattr(d.call, "__name__")
        ]
        assert "verify_service_account" in dep_names

    def test_get_pool_holds_requires_auth(self):
        from src.dbos_workflows.token_bucket.router import router

        holds_route = None
        for route in router.routes:
            if hasattr(route, "path") and "holds" in getattr(route, "path", ""):
                holds_route = route
                break
        assert holds_route is not None
        dep_names = [
            d.call.__name__
            for d in holds_route.dependant.dependencies
            if hasattr(d, "call") and hasattr(d.call, "__name__")
        ]
        assert "verify_service_account" in dep_names


class TestRouterUsesJoinedQuery:
    def test_no_local_compute_effective_capacity(self):
        import inspect

        import src.dbos_workflows.token_bucket.router as router_mod

        source = inspect.getsource(router_mod)
        assert "def _compute_effective_capacity" not in source

    def test_no_cross_module_capacity_import(self):
        import src.dbos_workflows.token_bucket.router as router_mod

        assert not hasattr(router_mod, "_get_effective_capacity")


class TestTokenPoolRouterPrefix:
    def test_router_mounted_with_api_prefix(self):
        from src.dbos_workflows.token_bucket.router import router

        assert router.prefix == "/admin/token-pools"
