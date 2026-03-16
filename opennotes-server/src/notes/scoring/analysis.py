from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.notes.models import Note
from src.notes.scoring.models import ScoringSnapshot
from src.notes.scoring.schemas import (
    NoteFactorData,
    RaterFactorData,
    ScoringAnalysisAttributes,
)
from src.simulation.models import SimAgent, SimAgentInstance
from src.users.profile_models import CommunityMember  # noqa: F401

logger = logging.getLogger(__name__)


async def _resolve_rater_identities(
    rater_ids: list[str],
    community_server_id: UUID,
    db: AsyncSession,
) -> dict[str, dict[str, str | None]]:
    if not rater_ids:
        return {}

    valid_uuids: list[UUID] = []
    for rid in rater_ids:
        try:
            valid_uuids.append(UUID(rid))
        except (ValueError, AttributeError):
            continue

    if not valid_uuids:
        return {}

    agents_result = await db.execute(select(SimAgent).where(SimAgent.id.in_(valid_uuids)))
    agents_by_id = {a.id: a for a in agents_result.scalars().all()}

    remaining_uuids = [u for u in valid_uuids if u not in agents_by_id]

    instance_by_profile: dict[UUID, SimAgentInstance] = {}
    if remaining_uuids:
        instances_result = await db.execute(
            select(SimAgentInstance)
            .where(SimAgentInstance.user_profile_id.in_(remaining_uuids))
            .options(selectinload(SimAgentInstance.agent_profile))
        )
        for inst in instances_result.scalars().all():
            instance_by_profile[inst.user_profile_id] = inst

    identity_map: dict[str, dict[str, str | None]] = {}
    for rid in rater_ids:
        try:
            uid = UUID(rid)
        except (ValueError, AttributeError):
            identity_map[rid] = {"agent_name": None, "personality": None, "short_description": None}
            continue

        agent = agents_by_id.get(uid)
        if agent:
            identity_map[rid] = {
                "agent_name": agent.name,
                "personality": agent.personality,
                "short_description": agent.short_description,
            }
        else:
            inst = instance_by_profile.get(uid)
            if inst and inst.agent_profile:
                identity_map[rid] = {
                    "agent_name": inst.agent_profile.name,
                    "personality": inst.agent_profile.personality,
                    "short_description": inst.agent_profile.short_description,
                }
            else:
                identity_map[rid] = {
                    "agent_name": None,
                    "personality": None,
                    "short_description": None,
                }

    return identity_map


async def _resolve_note_metadata(
    note_ids: list[str],
    community_server_id: UUID,
    db: AsyncSession,
) -> dict[str, dict[str, str | None]]:
    if not note_ids:
        return {}

    valid_uuids: list[UUID] = []
    for nid in note_ids:
        try:
            valid_uuids.append(UUID(nid))
        except (ValueError, AttributeError):
            continue

    if not valid_uuids:
        return {}

    notes_result = await db.execute(
        select(Note).where(
            Note.id.in_(valid_uuids),
            Note.community_server_id == community_server_id,
        )
    )

    note_map: dict[str, dict[str, str | None]] = {}
    author_ids: list[UUID] = []
    note_authors: dict[str, UUID] = {}

    for note in notes_result.scalars().all():
        nid_str = str(note.id)
        note_map[nid_str] = {
            "status": note.status,
            "classification": note.classification,
            "author_agent_name": None,
            "author_short_description": None,
        }
        author_ids.append(note.author_id)
        note_authors[nid_str] = note.author_id

    if author_ids:
        agents_result = await db.execute(select(SimAgent).where(SimAgent.id.in_(author_ids)))
        author_agent_map: dict[UUID, dict[str, str | None]] = {}
        for agent in agents_result.scalars().all():
            author_agent_map[agent.id] = {
                "name": agent.name,
                "short_description": agent.short_description,
            }

        remaining_author_ids = [a for a in author_ids if a not in author_agent_map]
        if remaining_author_ids:
            instances_result = await db.execute(
                select(SimAgentInstance)
                .where(SimAgentInstance.user_profile_id.in_(remaining_author_ids))
                .options(selectinload(SimAgentInstance.agent_profile))
            )
            for inst in instances_result.scalars().all():
                if inst.agent_profile:
                    author_agent_map[inst.user_profile_id] = {
                        "name": inst.agent_profile.name,
                        "short_description": inst.agent_profile.short_description,
                    }

        for nid_str, author_id in note_authors.items():
            agent_info = author_agent_map.get(author_id)
            if agent_info and nid_str in note_map:
                note_map[nid_str]["author_agent_name"] = agent_info["name"]
                note_map[nid_str]["author_short_description"] = agent_info.get("short_description")

    return note_map


async def compute_scoring_factor_analysis(
    community_server_id: UUID,
    db: AsyncSession,
) -> ScoringAnalysisAttributes | None:
    result = await db.execute(
        select(ScoringSnapshot).where(ScoringSnapshot.community_server_id == community_server_id)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        return None

    rater_ids = [r["rater_id"] for r in snapshot.rater_factors if "rater_id" in r]
    note_ids = [n["note_id"] for n in snapshot.note_factors if "note_id" in n]

    rater_identities = await _resolve_rater_identities(rater_ids, community_server_id, db)
    note_metadata = await _resolve_note_metadata(note_ids, community_server_id, db)

    rater_factors = []
    for rf in snapshot.rater_factors:
        rid = rf.get("rater_id", "")
        identity = rater_identities.get(
            rid, {"agent_name": None, "personality": None, "short_description": None}
        )
        rater_factors.append(
            RaterFactorData(
                rater_id=rid,
                agent_name=identity.get("agent_name"),
                personality=identity.get("personality"),
                short_description=identity.get("short_description"),
                intercept=rf.get("intercept") or 0.0,
                factor1=rf.get("factor1") or 0.0,
            )
        )

    note_factors = []
    for nf in snapshot.note_factors:
        nid = nf.get("note_id", "")
        meta = note_metadata.get(
            nid,
            {
                "status": None,
                "classification": None,
                "author_agent_name": None,
                "author_short_description": None,
            },
        )
        note_factors.append(
            NoteFactorData(
                note_id=nid,
                intercept=nf.get("intercept") or 0.0,
                factor1=nf.get("factor1") or 0.0,
                status=nf.get("status") or meta.get("status"),
                classification=meta.get("classification"),
                author_agent_name=meta.get("author_agent_name"),
                author_short_description=meta.get("author_short_description"),
            )
        )

    metadata = snapshot.metadata_ or {}

    return ScoringAnalysisAttributes(
        scored_at=snapshot.scored_at,
        tier=metadata.get("tier"),
        global_intercept=snapshot.global_intercept,
        rater_count=len(rater_factors),
        note_count=len(note_factors),
        rater_factors=rater_factors,
        note_factors=note_factors,
    )
