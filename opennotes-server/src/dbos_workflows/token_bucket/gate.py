from __future__ import annotations

import logging

from dbos import DBOS

from src.dbos_workflows.token_bucket.operations import release_tokens, try_acquire_tokens

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_WAIT = 300.0


class TokenGate:
    """Workflow-level helper that acquires and releases tokens from a pool.

    Usage inside a @DBOS.workflow():
        gate = TokenGate(pool="default", weight=5)
        gate.acquire()
        try:
            # ... do work ...
        finally:
            gate.release()
    """

    def __init__(
        self,
        pool: str = "default",
        weight: int = 1,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait_seconds: float = DEFAULT_MAX_WAIT,
        parent_holds_token: bool = False,
    ):
        self.pool = pool
        self.weight = weight
        self.poll_interval = poll_interval
        self.max_wait_seconds = max_wait_seconds
        self.parent_holds_token = parent_holds_token
        self._workflow_id: str | None = None

    def acquire(self) -> None:
        """Block until tokens are acquired. Must be called inside a DBOS workflow."""
        if self.parent_holds_token:
            logger.info(
                "TokenGate acquire skipped because parent workflow holds token",
                extra={"pool": self.pool, "weight": self.weight},
            )
            return
        wf_id = DBOS.workflow_id
        if wf_id is None:
            raise RuntimeError("TokenGate.acquire() must be called inside a DBOS workflow")
        elapsed = 0.0
        while True:
            try:
                acquired = try_acquire_tokens(self.pool, self.weight, wf_id)
            except Exception:
                logger.warning(
                    "try_acquire_tokens failed, will retry",
                    extra={"pool": self.pool, "workflow_id": wf_id, "elapsed": elapsed},
                    exc_info=True,
                )
                acquired = False
            if acquired:
                self._workflow_id = wf_id
                logger.info(
                    "Tokens acquired",
                    extra={
                        "pool": self.pool,
                        "weight": self.weight,
                        "workflow_id": wf_id,
                        "wait_seconds": elapsed,
                    },
                )
                return
            if elapsed >= self.max_wait_seconds:
                raise TimeoutError(
                    f"Token acquire timed out after {elapsed}s "
                    f"for pool={self.pool} weight={self.weight}"
                )
            DBOS.sleep(self.poll_interval)
            elapsed += self.poll_interval

    def release(self) -> None:
        """Release held tokens. Safe to call even if acquire was never called."""
        if self.parent_holds_token:
            return
        if self._workflow_id:
            release_tokens(self.pool, self._workflow_id)
