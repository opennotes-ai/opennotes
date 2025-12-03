"""
Conftest for integration tests.

Integration tests may or may not require database access depending on what they test.
Tests that need database will use it, tests that don't need it won't use it.
"""

import pytest


def pytest_runtest_setup(item):
    """
    Hook that runs before each test to reset database state.

    With asyncio_default_fixture_loop_scope=function, each test gets a fresh
    event loop. The async engine and session_maker are bound to the loop they
    were created in. To avoid "Task got Future attached to a different loop"
    errors, we reset the module-level database engine and session_maker before
    each test so the next get_engine()/get_session_maker() call creates new
    ones bound to the current test's event loop.

    This is called even before fixture setup, ensuring the reset happens
    before any test fixtures are resolved.
    """
    from src.database import _reset_database_for_test_loop

    _reset_database_for_test_loop()


@pytest.fixture(autouse=True)
async def cleanup_database_after_test():
    """
    Clean up database connections after each test.

    Runs in the fixture teardown phase, after the test and all its fixtures
    have completed. Properly disposes the async engine to ensure all async
    connection cancellations are awaited, preventing unawaited coroutine warnings.
    """
    yield

    import asyncio

    from src.database import get_engine

    engine = get_engine()
    if engine is not None:
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed() and loop.is_running():
                await engine.dispose()
            else:
                print("   Event loop is closed or not running, skipping engine.dispose()")
        except RuntimeError:
            print("   No running event loop, skipping engine.dispose()")
