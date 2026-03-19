import asyncio
import threading

from src.database import _reset_database_for_test_loop, get_engine, get_session_maker
from src.utils.async_compat import reset, run_sync


class TestPerLoopEngineIntegration:
    def setup_method(self):
        _reset_database_for_test_loop()

    def teardown_method(self):
        _reset_database_for_test_loop()
        reset()

    def test_run_sync_gets_different_engine_than_main_loop(self):
        async def get_engine_id_on_bg_loop() -> int:
            engine = get_engine()
            return id(engine)

        async def outer() -> None:
            main_engine = get_engine()
            main_id = id(main_engine)
            bg_engine_id = run_sync(get_engine_id_on_bg_loop())
            assert main_id != bg_engine_id, (
                "Main loop and background loop should have different engines"
            )

        asyncio.run(outer())

    def test_run_sync_reuses_engine_across_calls(self):
        async def get_engine_id() -> int:
            return id(get_engine())

        id1 = run_sync(get_engine_id())
        id2 = run_sync(get_engine_id())
        id3 = run_sync(get_engine_id())
        assert id1 == id2 == id3, "Same background loop should reuse engine"

    def test_concurrent_run_sync_with_db_no_loop_mismatch(self):
        errors: list[Exception] = []

        async def db_work() -> str:
            maker = get_session_maker()
            loop_id = id(asyncio.get_running_loop())
            return f"loop={loop_id},maker={id(maker)}"

        async def outer() -> None:
            threads = []
            for _ in range(10):

                def submit():
                    try:
                        run_sync(db_work())
                    except Exception as e:
                        errors.append(e)

                t = threading.Thread(target=submit)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        asyncio.run(outer())
        assert not errors, f"Concurrent run_sync errors: {errors}"

    def test_stale_loop_entry_cleaned_up(self):
        temp_loop = asyncio.new_event_loop()
        temp_thread = threading.Thread(target=temp_loop.run_forever, daemon=True)
        temp_thread.start()

        async def get_engine_on_temp() -> int:
            return id(get_engine())

        future = asyncio.run_coroutine_threadsafe(get_engine_on_temp(), temp_loop)
        future.result(timeout=5)

        temp_loop.call_soon_threadsafe(temp_loop.stop)
        temp_thread.join(timeout=5)
        temp_loop.close()

        from src import database

        stale_key = id(temp_loop)
        assert stale_key in database._engines
        _, tracked = database._engines[stale_key]
        assert tracked is not None
        assert tracked.is_closed()

        cleanup_loop = asyncio.new_event_loop()
        cleanup_thread = threading.Thread(target=cleanup_loop.run_forever, daemon=True)
        cleanup_thread.start()

        async def trigger_cleanup() -> int:
            return id(get_engine())

        try:
            future2 = asyncio.run_coroutine_threadsafe(trigger_cleanup(), cleanup_loop)
            future2.result(timeout=5)

            assert stale_key not in database._engines, "Closed loop entries should be cleaned up"
        finally:
            cleanup_loop.call_soon_threadsafe(cleanup_loop.stop)
            cleanup_thread.join(timeout=5)
            cleanup_loop.close()

    def test_different_loops_get_different_session_makers(self):
        async def get_maker_id_on_bg_loop() -> int:
            return id(get_session_maker())

        async def outer() -> None:
            main_maker = get_session_maker()
            main_id = id(main_maker)
            bg_maker_id = run_sync(get_maker_id_on_bg_loop())
            assert main_id != bg_maker_id, (
                "Main loop and background loop should have different session makers"
            )

        asyncio.run(outer())
