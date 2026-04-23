"""Async pipeline job helpers (TASK-1473).

Section slot write-contract helpers and job finalization. Centralizes the
`jsonb_build_object` merge pattern + CAS guards so section workers and
retry handlers never duplicate SQL.
"""
from __future__ import annotations

from src.jobs.finalize import maybe_finalize_job
from src.jobs.slots import claim_slot, mark_slot_done, mark_slot_failed, write_slot

__all__ = [
    "claim_slot",
    "mark_slot_done",
    "mark_slot_failed",
    "maybe_finalize_job",
    "write_slot",
]
