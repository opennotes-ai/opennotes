"""Schemas local to the flashpoint (tone) analysis.

Kept in a leading-underscore module so BE-7 (SCD) can land sibling
schemas alongside without merge conflicts in a shared ``schemas.py``.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Categorical risk level for conversation flashpoint detection."""

    LOW_RISK = "Low Risk"
    GUARDED = "Guarded"
    HEATED = "Heated"
    HOSTILE = "Hostile"
    DANGEROUS = "Dangerous"


class FlashpointMatch(BaseModel):
    """Match result from flashpoint detection for a single utterance.

    Port of ``ConversationFlashpointMatch`` from opennotes-server, adapted
    for the vibecheck utterance model: ``utterance_id`` replaces Discord
    ``message_id``; other fields are unchanged.
    """

    scan_type: Literal["conversation_flashpoint"] = "conversation_flashpoint"
    utterance_id: str = Field(
        ..., description="Platform-agnostic identifier of the scored utterance"
    )
    derailment_score: int = Field(
        ..., ge=0, le=100, description="Derailment risk score (0-100)"
    )
    risk_level: RiskLevel = Field(..., description="Categorical risk assessment level")
    reasoning: str = Field(..., description="Explanation of detected escalation signals")
    context_messages: int = Field(
        ..., ge=0, description="Number of context messages analyzed"
    )
