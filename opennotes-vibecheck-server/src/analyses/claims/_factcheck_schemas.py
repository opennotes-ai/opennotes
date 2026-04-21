"""Schemas for Google Fact Check Tools API matches.

Kept local to the claims analysis module (under a `_factcheck_schemas.py`
name) to avoid import-surface conflicts with BE-5's claim-extraction
schemas in `_claims_schemas.py`. The orchestrator aggregates these
sub-schemas into the final `SidebarPayload`.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class FactCheckMatch(BaseModel):
    """A single fact-check article surfaced by the Google Fact Check Tools API.

    One claim (as extracted+deduped from an utterance) can map to multiple
    `FactCheckMatch` rows — each corresponding to one `claimReview` entry
    returned by the API. We keep the original claim text alongside the
    reviewer-supplied metadata so the UI can show provenance clearly.
    """

    claim_text: str
    publisher: str
    review_title: str
    review_url: str
    textual_rating: str
    review_date: date | None = None
