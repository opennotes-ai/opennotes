import logging
import random
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import pendulum
from pydantic_ai import Agent, RunContext, WebSearchTool
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.model_id import ModelId
from src.notes.models import Note, Rating, Request
from src.simulation.models import SimAgentInstance, SimChannelMessage
from src.simulation.schemas import ActionSelectionResult, SimActionType, SimAgentAction

logger = logging.getLogger(__name__)

MAX_PERSONALITY_CHARS: int = 500
MAX_CONTEXT_REQUESTS: int = 5
MAX_CONTEXT_NOTES: int = 10
MAX_LINKED_NOTES_PER_REQUEST: int = 10
MAX_CHANNEL_MESSAGE_LENGTH: int = 2000
CHANNEL_RATE_LIMIT_WINDOW_SECONDS: int = 60
CHANNEL_RATE_LIMIT_MAX: int = 3
CHANNEL_SIMILARITY_THRESHOLD: float = 0.8
CHANNEL_SIMILARITY_LOOKBACK: int = 5
TOKEN_BUDGET: int = 16000
MAX_RATE_NOTES_BATCH: int = 5


_DEFAULT_MODEL = ModelId.from_pydantic_ai("openai:gpt-4o-mini")


@dataclass
class SimAgentDeps:
    db: AsyncSession
    community_server_id: UUID
    agent_instance_id: UUID
    user_profile_id: UUID
    available_requests: list[dict]
    available_notes: list[dict]
    agent_personality: str
    model_name: ModelId
    tool_config: dict[str, Any] | None = field(default=None)
    simulation_run_id: UUID | None = None
    agent_profile_id: UUID | None = None


WEBSEARCH_SUPPORTED_PROVIDERS = frozenset({"anthropic", "google", "groq"})


def _is_research_available(deps: SimAgentDeps) -> bool:
    tc = deps.tool_config
    return bool(
        tc
        and tc.get("research_enabled")
        and deps.model_name.provider in WEBSEARCH_SUPPORTED_PROVIDERS
    )


sim_agent: Agent[SimAgentDeps, SimAgentAction] = Agent(
    deps_type=SimAgentDeps,
    output_type=SimAgentAction,
    retries=3,
    instrument=True,
)


action_selector: Agent[SimAgentDeps, ActionSelectionResult] = Agent(
    deps_type=SimAgentDeps,
    output_type=ActionSelectionResult,
    retries=3,
    instrument=True,
)


@action_selector.system_prompt
def build_action_selector_instructions(ctx: RunContext[SimAgentDeps]) -> str:
    personality = _truncate_personality(ctx.deps.agent_personality)
    base = (
        "You are deciding what action to take this turn in a Community Notes simulation.\n\n"
        f"Your personality: {personality}\n\n"
        "Choose exactly one action:\n"
        "- write_note: Write a community note for one of the available content requests\n"
        "- rate_note: Rate 1-5 of the available community notes on helpfulness\n"
        "- pass_turn: Skip this turn (only when no content requests or notes are available)\n\n"
        "IMPORTANT: If notes are available to rate, you should rate one rather than passing.\n\n"
        "Respond with your chosen action_type and a brief reasoning."
    )

    if _is_research_available(ctx.deps):
        base += (
            "\n\nNote: You can use web search during any action to verify "
            "claims or gather evidence. You may also choose pass_turn after "
            "researching to store findings for future turns."
        )

    return base


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _truncate_personality(personality: str, max_chars: int = MAX_PERSONALITY_CHARS) -> str:
    if len(personality) <= max_chars:
        return personality
    return personality[:max_chars].rsplit(" ", 1)[0] + "..."


@sim_agent.system_prompt
def build_instructions(ctx: RunContext[SimAgentDeps]) -> str:
    personality = _truncate_personality(ctx.deps.agent_personality)
    base = (
        "You are a Community Notes participant in a simulation. "
        "Your goal is to evaluate content and contribute helpful, "
        "accurate community notes.\n\n"
        f"Your personality and approach:\n{personality}\n\n"
        "Available actions:\n"
        "- write_note: Write a new community note for a request\n"
        "- rate_note: Rate existing community notes\n"
        "- list_requests: List available requests with IDs and content\n"
        "- list_my_actions: List requests you've already written notes for\n"
        "- pass_turn: Do nothing this turn\n\n"
        "Choose the most appropriate action based on the available "
        "requests and notes. Always explain your reasoning."
    )

    base += (
        "\n\nRequest statuses: PENDING — needs notes, "
        "IN_PROGRESS — being worked on, "
        "COMPLETED — has helpful note but more perspectives welcome.\n"
    )

    if ctx.deps.simulation_run_id is not None:
        base += (
            "\n\nChannel tools:\n"
            "- post_to_channel: Share research findings, flag patterns, "
            "express uncertainty, or coordinate with other agents\n"
            "- read_channel: Read recent messages from the shared agent channel"
        )

    if _is_research_available(ctx.deps):
        base += (
            "\n\nResearch tools:\n"
            "You have access to web search. Use it to verify claims, "
            "gather evidence, or understand context before writing or rating notes. "
            "You can also spend a turn purely researching — search for information "
            "and then pass your turn. Research results persist in your memory "
            "and will be available in future turns."
        )

    return base


@sim_agent.tool
async def write_note(  # noqa: PLR0911
    ctx: RunContext[SimAgentDeps],
    request_id: str,
    summary: str,
    classification: str,
) -> str:
    """Write a new community note for a request. Use this when you see a request
    that needs context or fact-checking. Classification must be one of:
    NOT_MISLEADING or MISINFORMED_OR_POTENTIALLY_MISLEADING."""
    try:
        req_result = await ctx.deps.db.execute(
            select(Request.id).where(
                Request.id == UUID(request_id),
                Request.community_server_id == ctx.deps.community_server_id,
                Request.status != "FAILED",
                Request.deleted_at.is_(None),
            )
        )
        if req_result.scalar_one_or_none() is None:
            return f"Error: request id '{request_id}' not found or is not available."
    except (ValueError, SQLAlchemyError):
        return f"Error: request id '{request_id}' not found or is not available."

    if ctx.deps.agent_profile_id and ctx.deps.simulation_run_id:
        sibling_ids_subq = (
            select(SimAgentInstance.user_profile_id)
            .where(
                SimAgentInstance.agent_profile_id == ctx.deps.agent_profile_id,
                SimAgentInstance.simulation_run_id == ctx.deps.simulation_run_id,
            )
            .scalar_subquery()
        )
        existing_note = await ctx.deps.db.execute(
            select(Note.id)
            .where(
                Note.request_id == UUID(request_id),
                Note.author_id.in_(sibling_ids_subq),
                Note.deleted_at.is_(None),
            )
            .limit(1)
        )
        if existing_note.scalar_one_or_none() is not None:
            return "Error: you have already written a note for this request."

    valid_classifications = {"NOT_MISLEADING", "MISINFORMED_OR_POTENTIALLY_MISLEADING"}
    if classification not in valid_classifications:
        return (
            f"Error: classification '{classification}' is invalid. "
            f"Must be one of: {', '.join(sorted(valid_classifications))}"
        )

    note = Note(
        request_id=UUID(request_id),
        author_id=ctx.deps.user_profile_id,
        summary=summary,
        classification=classification,
        status="NEEDS_MORE_RATINGS",
        community_server_id=ctx.deps.community_server_id,
        ai_generated=True,
        ai_provider=ctx.deps.model_name.provider,
        ai_model=ctx.deps.model_name.model,
    )
    ctx.deps.db.add(note)
    try:
        await ctx.deps.db.flush()
    except IntegrityError:
        await ctx.deps.db.rollback()
        logger.exception("Integrity error creating note for request %s", request_id)
        return "Error: could not create note due to a constraint violation."
    except SQLAlchemyError:
        await ctx.deps.db.rollback()
        logger.exception("Database error creating note for request %s", request_id)
        return "Error: could not create note due to a database error."

    return f"Note created for request {request_id} with classification '{classification}'."


@sim_agent.tool
async def rate_notes(
    ctx: RunContext[SimAgentDeps],
    ratings: list[dict[str, str]],
) -> str:
    """Rate one or more community notes in a single call. Each entry must have
    'note_id' and 'helpfulness_level'. helpfulness_level must be one of:
    HELPFUL, SOMEWHAT_HELPFUL, NOT_HELPFUL. You can rate between 1 and 5 notes."""
    if not ratings or len(ratings) > MAX_RATE_NOTES_BATCH:
        return (
            f"Error: ratings must contain between 1 and {MAX_RATE_NOTES_BATCH} entries, "
            f"got {len(ratings)}."
        )

    valid_ids = {str(n["note_id"]) for n in ctx.deps.available_notes}
    valid_levels = {"HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"}
    results: list[str] = []

    for entry in ratings:
        note_id = entry.get("note_id", "")
        helpfulness_level = entry.get("helpfulness_level", "")

        if note_id not in valid_ids:
            results.append(f"Error: note_id '{note_id}' not found in available notes.")
            continue

        if helpfulness_level not in valid_levels:
            results.append(
                f"Error: helpfulness_level '{helpfulness_level}' is invalid. "
                f"Must be one of: {', '.join(sorted(valid_levels))}"
            )
            continue

        try:
            note_uuid = UUID(note_id)
        except ValueError:
            results.append(f"Error: note_id '{note_id}' is not a valid UUID.")
            continue

        stmt = (
            insert(Rating)
            .values(
                rater_id=ctx.deps.user_profile_id,
                note_id=note_uuid,
                helpfulness_level=helpfulness_level,
            )
            .on_conflict_do_update(
                index_elements=["note_id", "rater_id"],
                set_={
                    "helpfulness_level": helpfulness_level,
                    "updated_at": func.now(),
                },
            )
        )
        try:
            async with ctx.deps.db.begin_nested():
                await ctx.deps.db.execute(stmt)
                await ctx.deps.db.flush()
            results.append(f"Rated note '{note_id}' as '{helpfulness_level}'.")
        except IntegrityError:
            logger.exception("Integrity error creating rating for note %s", note_id)
            results.append(f"Error rating '{note_id}': constraint violation.")
        except SQLAlchemyError:
            logger.exception("Database error creating rating for note %s", note_id)
            results.append(f"Error rating '{note_id}': database error.")

    return "\n".join(results)


@sim_agent.tool_plain
def pass_turn() -> str:
    """Do nothing this turn. Use this when no action seems appropriate
    given the current context."""
    return "Turn passed. No action taken."


async def _check_channel_dedup(
    db: AsyncSession,
    agent_instance_id: UUID,
    simulation_run_id: UUID,
    message: str,
) -> str | None:
    cutoff = pendulum.now("UTC").subtract(seconds=CHANNEL_RATE_LIMIT_WINDOW_SECONDS)
    rate_stmt = (
        select(func.count())
        .select_from(SimChannelMessage)
        .where(
            SimChannelMessage.agent_instance_id == agent_instance_id,
            SimChannelMessage.simulation_run_id == simulation_run_id,
            SimChannelMessage.created_at > cutoff,
        )
    )
    rate_result = await db.execute(rate_stmt)
    recent_count = rate_result.scalar_one()
    if recent_count >= CHANNEL_RATE_LIMIT_MAX:
        return "Rate limit: please wait before posting again."

    sim_stmt = (
        select(SimChannelMessage.message_text)
        .where(
            SimChannelMessage.agent_instance_id == agent_instance_id,
            SimChannelMessage.simulation_run_id == simulation_run_id,
        )
        .order_by(SimChannelMessage.created_at.desc())
        .limit(CHANNEL_SIMILARITY_LOOKBACK)
    )
    sim_result = await db.execute(sim_stmt)
    recent_texts = sim_result.scalars().all()
    for recent_text in recent_texts:
        if SequenceMatcher(None, message, recent_text).ratio() > CHANNEL_SIMILARITY_THRESHOLD:
            return "Message too similar to a recent post. Try a different message."

    return None


@sim_agent.tool
async def post_to_channel(
    ctx: RunContext[SimAgentDeps],
    message: str,
) -> str:
    """Post a message to the shared agent channel. Use this to share research
    findings, flag patterns, express uncertainty, or coordinate with other agents."""
    if ctx.deps.simulation_run_id is None:
        return "Error: channel not available (no simulation_run_id)."

    if not message or not message.strip():
        return "Error: message cannot be empty or whitespace-only."

    if len(message) > MAX_CHANNEL_MESSAGE_LENGTH:
        return (
            f"Error: message too long ({len(message)} chars). "
            f"Maximum is {MAX_CHANNEL_MESSAGE_LENGTH} characters."
        )

    dedup_error = await _check_channel_dedup(
        ctx.deps.db,
        ctx.deps.agent_instance_id,
        ctx.deps.simulation_run_id,
        message,
    )
    if dedup_error:
        return dedup_error

    msg = SimChannelMessage(
        simulation_run_id=ctx.deps.simulation_run_id,
        agent_instance_id=ctx.deps.agent_instance_id,
        message_text=message,
    )
    ctx.deps.db.add(msg)
    try:
        await ctx.deps.db.flush()
    except SQLAlchemyError:
        await ctx.deps.db.rollback()
        logger.exception("Database error posting to channel")
        return "Error: could not post to channel due to a database error."
    return "Posted to channel."


@sim_agent.tool
async def read_channel(
    ctx: RunContext[SimAgentDeps],
) -> str:
    """Read recent messages from the shared agent channel."""
    if ctx.deps.simulation_run_id is None:
        return "Channel not available."

    query = (
        select(SimChannelMessage)
        .where(SimChannelMessage.simulation_run_id == ctx.deps.simulation_run_id)
        .order_by(SimChannelMessage.created_at.desc())
        .limit(20)
    )
    try:
        result = await ctx.deps.db.execute(query)
    except SQLAlchemyError:
        await ctx.deps.db.rollback()
        logger.exception("Database error reading channel")
        return "Error: could not read channel due to a database error."
    messages = result.scalars().all()

    if not messages:
        return "No channel messages yet."

    lines = []
    for msg in reversed(messages):
        short_id = str(msg.agent_instance_id)[:8]
        lines.append(f"[Agent {short_id}]: {msg.message_text}")
    return "\n".join(lines)


MAX_LIST_REQUESTS = 20

VALID_REQUEST_STATUSES = frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"})


@sim_agent.tool
async def list_requests(
    ctx: RunContext[SimAgentDeps],
    status: str = "",
    include_acted_on: str = "",
) -> str:
    """List available content requests with their IDs and content preview.
    Use the returned ID in write_note to create a community note.
    Optional status filter (default: all non-FAILED).
    Set include_acted_on to 'true' to also show requests you already wrote notes for."""
    if status and status not in VALID_REQUEST_STATUSES:
        return (
            f"Error: invalid status '{status}'. "
            f"Must be one of: {', '.join(sorted(VALID_REQUEST_STATUSES))}"
        )

    sibling_noted_reqs = None
    sibling_ids_subq = None
    if ctx.deps.agent_profile_id and ctx.deps.simulation_run_id:
        sibling_ids_subq = (
            select(SimAgentInstance.user_profile_id)
            .where(
                SimAgentInstance.agent_profile_id == ctx.deps.agent_profile_id,
                SimAgentInstance.simulation_run_id == ctx.deps.simulation_run_id,
            )
            .scalar_subquery()
        )
        sibling_noted_reqs = select(Note.request_id).where(
            Note.author_id.in_(sibling_ids_subq),
            Note.deleted_at.is_(None),
        )

    note_count_subq = (
        select(func.count(Note.id))
        .where(
            Note.request_id == Request.id,
            Note.deleted_at.is_(None),
        )
        .correlate(Request)
        .scalar_subquery()
        .label("note_count")
    )

    if status:
        query = (
            select(Request, note_count_subq)
            .where(
                Request.community_server_id == ctx.deps.community_server_id,
                Request.status == status,
                Request.deleted_at.is_(None),
            )
            .order_by(Request.created_at.desc())
            .limit(MAX_LIST_REQUESTS)
        )
    else:
        query = (
            select(Request, note_count_subq)
            .where(
                Request.community_server_id == ctx.deps.community_server_id,
                Request.status != "FAILED",
                Request.deleted_at.is_(None),
            )
            .order_by(Request.created_at.desc())
            .limit(MAX_LIST_REQUESTS)
        )

    if sibling_noted_reqs is not None and not include_acted_on:
        query = query.where(Request.id.notin_(sibling_noted_reqs))

    try:
        result = await ctx.deps.db.execute(query)
        rows = result.all()
    except SQLAlchemyError:
        await ctx.deps.db.rollback()
        logger.exception("Database error listing requests")
        return "Error: could not list requests due to a database error."

    if not rows:
        label = status if status else "non-FAILED"
        return f"No {label} requests found."

    acted_on_ids: set = set()
    if sibling_noted_reqs is not None and sibling_ids_subq is not None and include_acted_on:
        try:
            acted_result = await ctx.deps.db.execute(
                select(Note.request_id).where(
                    Note.author_id.in_(sibling_ids_subq),
                    Note.deleted_at.is_(None),
                )
            )
            acted_on_ids = {row[0] for row in acted_result.all()}
        except SQLAlchemyError:
            logger.exception("Database error fetching acted-on requests")

    label = status if status else "available"
    lines = [f"{len(rows)} {label} request(s):\n"]
    for req, note_count in rows:
        content = req.content or ""
        if len(content) > 100:
            content = content[:100].rsplit(" ", 1)[0] + "..."
        suffix = " (acted on)" if req.id in acted_on_ids else ""
        lines.append(f"- ID: {req.id}{suffix}\n  Content: {content}\n  Notes: {note_count}")

    return "\n".join(lines)


@sim_agent.tool
async def list_my_actions(
    ctx: RunContext[SimAgentDeps],
) -> str:
    """List requests you have already written notes for in this simulation."""
    try:
        if ctx.deps.agent_profile_id and ctx.deps.simulation_run_id:
            author_filter = Note.author_id.in_(
                select(SimAgentInstance.user_profile_id).where(
                    SimAgentInstance.agent_profile_id == ctx.deps.agent_profile_id,
                    SimAgentInstance.simulation_run_id == ctx.deps.simulation_run_id,
                )
            )
        else:
            author_filter = Note.author_id == ctx.deps.user_profile_id

        query = (
            select(Note, Request)
            .join(Request, Note.request_id == Request.id)
            .where(
                author_filter,
                Note.deleted_at.is_(None),
                Note.community_server_id == ctx.deps.community_server_id,
            )
            .order_by(Note.created_at.desc())
            .limit(MAX_LIST_REQUESTS)
        )
        result = await ctx.deps.db.execute(query)
        rows = result.all()
    except SQLAlchemyError:
        await ctx.deps.db.rollback()
        logger.exception("Database error listing my actions")
        return "Error: could not list your actions due to a database error."

    if not rows:
        return "You have not written any notes yet."

    lines = [f"{len(rows)} note(s) you have written:\n"]
    for note, req in rows:
        content = (req.content or "")[:80]
        if len(req.content or "") > 80:
            content = content.rsplit(" ", 1)[0] + "..."
        lines.append(
            f"- Request: {req.id}\n  Content: {content}\n  Your note: {(note.summary or '')[:60]}"
        )
    return "\n".join(lines)


BRIEF_MAX_TITLES = 3
BRIEF_TRUNCATE = 50
VERBOSE_TRUNCATE = 100


def _pluralize(count: int, singular: str) -> str:
    return f"{count} {singular}" if count == 1 else f"{count} {singular}s"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def _requests_label(n_req: int, n_notes: int) -> str:
    if n_req == 0 and n_notes > 0:
        return (
            f"No content requests \u2014 but {_pluralize(n_notes, 'note')} available to rate below."
        )
    if n_req == 0:
        return "No content requests to write notes for."
    if n_req == 1:
        return "1 content request to write a note for:"
    return f"{n_req} content requests to write notes for:"


def _notes_label(n_notes: int) -> str | None:
    if n_notes == 0:
        return "No notes available to rate."
    if n_notes == 1:
        return "1 note available to rate:"
    return f"{n_notes} notes available to rate:"


def build_queue_summary(
    requests: list[dict],
    notes: list[dict],
    verbose: bool = False,
) -> str:
    max_titles = None if verbose else BRIEF_MAX_TITLES
    trunc = VERBOSE_TRUNCATE if verbose else BRIEF_TRUNCATE

    lines: list[str] = []
    n_req = len(requests)
    n_notes = len(notes)

    lines.append(_requests_label(n_req, n_notes))

    shown_requests = requests if max_titles is None else requests[:max_titles]
    for req in shown_requests:
        lines.append(f"  - {_truncate(req.get('content') or '', trunc)}")
    if max_titles is not None and n_req > max_titles:
        lines.append(f"  ...and {n_req - max_titles} more")

    note_label = _notes_label(n_notes)
    if note_label is not None:
        lines.append(note_label)

    if n_notes > 0:
        shown_notes = notes if max_titles is None else notes[:max_titles]
        for note in shown_notes:
            lines.append(f"  - {_truncate(note.get('summary') or '', trunc)}")
        if max_titles is not None and n_notes > max_titles:
            lines.append(f"  ...and {n_notes - max_titles} more")

    return "\n".join(lines)


PHASE1_DIVERSITY_THRESHOLD = 3


class OpenNotesSimAgent:
    def __init__(self, model: ModelId = _DEFAULT_MODEL):
        self._agent = sim_agent
        self._action_selector = action_selector
        self._model = model

    async def select_action(
        self,
        deps: SimAgentDeps,
        recent_actions: list[str],
        requests: list[dict],
        notes: list[dict],
        message_history: list[ModelMessage] | None = None,
    ) -> tuple[ActionSelectionResult, list[ModelMessage]]:
        brief_summary = build_queue_summary(requests, notes, verbose=False)
        prompt = self._build_phase1_prompt(
            recent_actions,
            brief_summary,
            requests_count=len(requests),
            notes_count=len(notes),
        )

        history_copy = list(message_history) if message_history else None

        result = await self._action_selector.run(
            prompt,
            deps=deps,
            message_history=history_copy,
            model=self._model.to_pydantic_ai(),
        )

        has_work = len(requests) > 0 or len(notes) > 0
        if not has_work:
            return result.output, result.all_messages()

        if result.output.action_type == SimActionType.PASS_TURN:
            verbose_summary = build_queue_summary(requests, notes, verbose=True)
            retry_prompt = self._build_phase1_prompt(
                recent_actions,
                verbose_summary,
                requests_count=len(requests),
                notes_count=len(notes),
            )
            result = await self._action_selector.run(
                retry_prompt,
                deps=deps,
                message_history=list(message_history) if message_history else None,
                model=self._model.to_pydantic_ai(),
            )

        has_notes = len(notes) > 0
        has_requests = len(requests) > 0
        if result.output.action_type == SimActionType.PASS_TURN and (has_notes or has_requests):
            parts: list[str] = []
            if has_notes:
                verb = "is" if len(notes) == 1 else "are"
                note_word = "note" if len(notes) == 1 else "notes"
                parts.append(f"There {verb} {len(notes)} {note_word} available to rate.")
            if has_requests:
                verb = "is" if len(requests) == 1 else "are"
                req_word = "content request" if len(requests) == 1 else "content requests"
                parts.append(f"There {verb} {len(requests)} {req_word} to write notes for.")
            nudge_prompt = (
                " ".join(parts)
                + " Are you sure you want to pass? Consider choosing "
                + ("rate_note" if has_notes else "write_note")
                + " instead."
            )
            result = await self._action_selector.run(
                nudge_prompt,
                deps=deps,
                message_history=list(message_history) if message_history else None,
                model=self._model.to_pydantic_ai(),
            )

        return result.output, result.all_messages()

    async def run_turn(
        self,
        deps: SimAgentDeps,
        message_history: list[ModelMessage] | None = None,
        usage_limits: UsageLimits | None = None,
        chosen_action_type: SimActionType | None = None,
    ) -> tuple[SimAgentAction, list[ModelMessage]]:
        if chosen_action_type is not None:
            prompt = self._build_phase2_prompt(
                chosen_action_type,
                deps.available_requests,
                deps.available_notes,
            )
        else:
            prompt = self._build_turn_prompt(deps)
        run_kwargs: dict[str, Any] = {
            "deps": deps,
            "message_history": message_history,
            "model": self._model.to_pydantic_ai(),
            "usage_limits": usage_limits or UsageLimits(request_limit=3, total_tokens_limit=16000),
        }

        if _is_research_available(deps):
            run_kwargs["builtin_tools"] = [WebSearchTool()]
        elif deps.tool_config and deps.tool_config.get("research_enabled"):
            logger.warning(
                "WebSearchTool requested but provider %r is not supported; skipping",
                deps.model_name.provider,
            )

        result = await self._agent.run(prompt, **run_kwargs)
        return result.output, result.all_messages()

    def _build_turn_prompt(
        self,
        deps: SimAgentDeps,
        token_budget: int = TOKEN_BUDGET,
    ) -> str:
        requests = deps.available_requests[:MAX_CONTEXT_REQUESTS]
        if len(deps.available_requests) > MAX_CONTEXT_REQUESTS:
            requests = random.sample(deps.available_requests, MAX_CONTEXT_REQUESTS)

        notes = deps.available_notes[:MAX_CONTEXT_NOTES]
        if len(deps.available_notes) > MAX_CONTEXT_NOTES:
            notes = random.sample(deps.available_notes, MAX_CONTEXT_NOTES)

        prompt = self._format_sections(requests, notes)

        while estimate_tokens(prompt) > token_budget and (requests or notes):
            if notes:
                notes.pop()
            elif requests:
                requests.pop()
            prompt = self._format_sections(requests, notes)

        return prompt

    def _build_phase2_prompt(
        self,
        action_type: SimActionType,
        requests: list[dict],
        notes: list[dict],
        token_budget: int = TOKEN_BUDGET,
    ) -> str:
        if action_type == SimActionType.PASS_TURN:
            return "You chose to pass this turn. No action needed."

        if action_type == SimActionType.WRITE_NOTE:
            items = list(requests[:MAX_CONTEXT_REQUESTS])
            if len(requests) > MAX_CONTEXT_REQUESTS:
                items = random.sample(requests, MAX_CONTEXT_REQUESTS)
            prompt = self._format_sections(items, [])
            while estimate_tokens(prompt) > token_budget and items:
                items.pop()
                prompt = self._format_sections(items, [])
            return prompt.replace(
                "Choose an action: write a note, rate notes, or pass.",
                "Write a community note for one of the requests above.",
            )

        if action_type == SimActionType.RATE_NOTE:
            items = list(notes[:MAX_CONTEXT_NOTES])
            if len(notes) > MAX_CONTEXT_NOTES:
                items = random.sample(notes, MAX_CONTEXT_NOTES)
            prompt = self._format_sections([], items)
            while estimate_tokens(prompt) > token_budget and items:
                items.pop()
                prompt = self._format_sections([], items)
            return prompt.replace(
                "Choose an action: write a note, rate notes, or pass.",
                "Rate between 1 and 5 of the notes above.",
            )

        return "You chose to pass this turn. No action needed."

    def _build_phase1_prompt(
        self,
        recent_actions: list[str],
        queue_summary: str,
        requests_count: int = 0,
        notes_count: int = 0,
    ) -> str:
        parts: list[str] = []
        has_work = requests_count > 0 or notes_count > 0
        if recent_actions:
            parts.append(
                f"Your recent actions (last {len(recent_actions)} turns): "
                f"{', '.join(recent_actions)}"
            )
            recent_tail = recent_actions[-PHASE1_DIVERSITY_THRESHOLD:]
            if (
                len(recent_tail) >= PHASE1_DIVERSITY_THRESHOLD
                and len(set(recent_tail)) == 1
                and recent_tail[-1] != "pass_turn"
            ):
                parts.append(
                    "You've been doing the same action repeatedly. "
                    "Consider trying a different action to diversify your contributions."
                )
            if recent_actions[-1] == "pass_turn" and has_work:
                parts.append(
                    "You passed last turn but there is work available. "
                    "Please write a note or rate one instead of passing."
                )
        if has_work:
            parts.append(f"\nAvailable work:\n{queue_summary}")
        else:
            parts.append("\nNo work is currently available.")
        parts.append(
            "\nWhat would you like to do this turn? Choose: write_note, rate_note, or pass_turn."
        )
        return "\n".join(parts)

    @staticmethod
    def _format_sections(requests: list[dict], notes: list[dict]) -> str:
        sections = ["Here is the current state of the community:\n"]
        if requests:
            sections.append("== Available Requests ==")
            for req in requests:
                block = (
                    f"- Request ID: {req['id']}\n"
                    f"  Content: {req.get('content', 'N/A')}\n"
                    f"  Status: {req.get('status', 'N/A')}"
                )
                req_notes = req.get("notes", [])
                if req_notes:
                    block += f"\n  Existing notes ({len(req_notes)}):"
                    for rn in req_notes:
                        summary = rn.get("summary") or ""
                        if len(summary) > 100:
                            summary = summary[:100].rsplit(" ", 1)[0] + "..."
                        block += f"\n    - [{rn.get('classification', 'N/A')}] {summary}"
                sections.append(block)
        else:
            sections.append("== No requests available ==")
        sections.append("")
        if notes:
            sections.append("== Existing Notes ==")
            for note in notes:
                sections.append(
                    f"- Note ID: {note['note_id']}\n"
                    f"  Summary: {note.get('summary', 'N/A')}\n"
                    f"  Classification: {note.get('classification', 'N/A')}\n"
                    f"  Status: {note.get('status', 'N/A')}"
                )
        else:
            sections.append("== No notes available ==")
        sections.append("\nChoose an action: write a note, rate notes, or pass.")
        return "\n".join(sections)


__all__ = [
    "CHANNEL_RATE_LIMIT_MAX",
    "CHANNEL_RATE_LIMIT_WINDOW_SECONDS",
    "CHANNEL_SIMILARITY_LOOKBACK",
    "CHANNEL_SIMILARITY_THRESHOLD",
    "MAX_CHANNEL_MESSAGE_LENGTH",
    "MAX_CONTEXT_NOTES",
    "MAX_CONTEXT_REQUESTS",
    "MAX_LINKED_NOTES_PER_REQUEST",
    "MAX_PERSONALITY_CHARS",
    "MAX_RATE_NOTES_BATCH",
    "PHASE1_DIVERSITY_THRESHOLD",
    "TOKEN_BUDGET",
    "WEBSEARCH_SUPPORTED_PROVIDERS",
    "OpenNotesSimAgent",
    "SimAgentDeps",
    "_is_research_available",
    "action_selector",
    "build_action_selector_instructions",
    "build_queue_summary",
    "estimate_tokens",
    "list_my_actions",
    "list_requests",
    "post_to_channel",
    "rate_notes",
    "read_channel",
    "sim_agent",
]
