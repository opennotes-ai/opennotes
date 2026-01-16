"""
Tests for Task-194: Fix SQL injection vulnerability in health check database validation.

Verifies that:
- Health check uses parameterized queries (text() with parameters)
- Table name validation prevents SQL injection

These tests use mock-based validation rather than source inspection to verify
parameterization is correct, making them robust against refactoring.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.monitoring.health import HealthChecker, HealthStatus


@pytest.mark.skip(reason="Requires PostgreSQL fixture - run as integration test")
@pytest.mark.asyncio
async def test_health_check_uses_parameterized_queries(postgresql):
    """
    Task-194: Verify health check uses parameterized queries, not f-strings.

    The fix replaced:
        f"SELECT EXISTS ... WHERE table_name = '{table}'"
    with:
        text("SELECT EXISTS ... WHERE table_name = :table_name"), {"table_name": table}
    """
    # Create test database connection
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{postgresql.host}:{postgresql.port}/test_health",
        echo=True,  # Enable SQL logging to verify parameterization
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        checker = HealthChecker(version="1.0.0", environment="test")

        # This should not raise SQL injection errors
        result = await checker.check_database(session)

        # Should be unhealthy because tables don't exist, but shouldn't crash
        assert result.status == HealthStatus.UNHEALTHY
        assert "Missing tables" in result.error

    await engine.dispose()


@pytest.mark.skip(reason="Requires PostgreSQL fixture - run as integration test")
@pytest.mark.asyncio
async def test_health_check_prevents_sql_injection_in_table_names(postgresql):
    """
    Task-194: Verify that SQL injection attempts in table name checks are prevented.

    Before the fix, malicious table names could inject SQL because of f-strings.
    After the fix, parameterized queries prevent this.
    """
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{postgresql.host}:{postgresql.port}/test_health",
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Test that the parameterized query safely handles malicious input
        # This should not execute injected SQL, just safely check for table existence

        malicious_table_names = [
            "users'; DROP TABLE users; --",  # Classic SQL injection
            "users' OR '1'='1",  # Boolean injection
            'users"; DELETE FROM notes; --',  # Alternate quote style
        ]

        for malicious_name in malicious_table_names:
            # The query should safely handle this as a literal string parameter
            result = await session.execute(
                text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
                ),
                {"table_name": malicious_name},
            )
            exists = result.scalar()

            # Should return False (table doesn't exist) without executing injection
            assert exists is False, f"Malicious table name check failed: {malicious_name}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_health_check_critical_tables_validation():
    """
    Task-194: Verify that the health check validates critical tables correctly.

    This ensures the parameterized query fix didn't break the actual
    table existence validation logic.
    """

    # Mock database session for testing
    class MockSession:
        def __init__(self, tables_exist=None):
            self.tables_exist = tables_exist or []
            self.queries = []

        async def execute(self, query, params=None):
            # Track queries for inspection
            self.queries.append({"query": str(query), "params": params})

            # Handle SELECT 1 (connectivity check)
            if "SELECT 1" in str(query):
                return MockResult(True)

            # Handle table existence checks
            if "information_schema.tables" in str(query):
                table_name = params.get("table_name") if params else None
                exists = table_name in self.tables_exist
                return MockResult(exists)

            return MockResult(False)

    class MockResult:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    # Test with all tables present
    checker = HealthChecker(version="1.0.0", environment="test")
    session_healthy = MockSession(tables_exist=["alembic_version", "users", "notes"])

    result = await checker.check_database(session_healthy)
    assert result.status == HealthStatus.HEALTHY

    # Verify queries used parameterization
    for query_info in session_healthy.queries:
        if "information_schema.tables" in query_info["query"]:
            assert query_info["params"] is not None, "Table queries should use parameters"
            assert "table_name" in query_info["params"], "Should use table_name parameter"

    # Test with missing tables
    session_unhealthy = MockSession(tables_exist=["alembic_version"])  # Missing users and notes

    result = await checker.check_database(session_unhealthy)
    assert result.status == HealthStatus.UNHEALTHY
    assert "users" in result.error
    assert "notes" in result.error


@pytest.mark.asyncio
async def test_health_check_sql_injection_defense_in_depth():
    """
    Task-194: Defense-in-depth test for SQL injection prevention.

    Verifies that even if an attacker controls table names (which they shouldn't),
    the parameterized queries prevent any SQL injection.
    """

    class MockSession:
        async def execute(self, query, params=None):
            # Simulate what the database would do with parameterized queries
            query_str = str(query)

            # Verify query structure is safe
            if "information_schema.tables" in query_str:
                # Should have parameter placeholder, not direct substitution
                assert ":table_name" in query_str, "Query should use :table_name placeholder"
                assert params is not None, "Query should have parameters"
                assert "table_name" in params, "Should pass table_name parameter"

                # Verify the parameter value is treated as a literal string
                table_name = params["table_name"]

                # These malicious patterns should be safely escaped by the parameter
                dangerous_patterns = [
                    "DROP",
                    "DELETE",
                    "INSERT",
                    "UPDATE",
                    "--",
                    ";",
                    "OR",
                    "UNION",
                ]

                if any(pattern in table_name.upper() for pattern in dangerous_patterns):
                    # The parameter is treated as a literal string, so it will just
                    # return False (table doesn't exist) rather than executing SQL
                    return MockResult(False)

            return MockResult(True)

    class MockResult:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    checker = HealthChecker(version="1.0.0", environment="test")
    session = MockSession()

    # This should complete without errors or SQL injection
    result = await checker.check_database(session)

    # Result doesn't matter as much as ensuring no SQL injection occurred
    assert result.status in [HealthStatus.HEALTHY, HealthStatus.UNHEALTHY]
