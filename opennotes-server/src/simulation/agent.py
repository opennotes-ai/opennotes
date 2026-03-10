import logging
import random
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic_ai import Agent, RunContext, WebSearchTool
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm_config.model_id import ModelId
from src.notes.models import Note, Rating
from src.simulation.models import SimChannelMessage
from src.simulation.schemas import ActionSelectionResult, SimActionType, SimAgentAction

logger = logging.getLogger(__name__)

MAX_PERSONALITY_CHARS: int = 500
MAX_CONTEXT_REQUESTS: int = 5
MAX_CONTEXT_NOTES: int = 5
MAX_LINKED_NOTES_PER_REQUEST: int = 10
MAX_CHANNEL_MESSAGE_LENGTH: int = 2000
TOKEN_BUDGET: int = 4000


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
)


action_selector: Agent[SimAgentDeps, ActionSelectionResult] = Agent(
    deps_type=SimAgentDeps,
    output_type=ActionSelectionResult,
)


@action_selector.system_prompt
def build_action_selector_instructions(ctx: RunContext[SimAgentDeps]) -> str:
    personality = _truncate_personality(ctx.deps.agent_personality)
    base = (
        "You are deciding what action to take this turn in a Community Notes simulation.\n\n"
        f"Your personality: {personality}\n\n"
        "Choose exactly one action:\n"
        "- write_note: Write a community note for one of the available content requests\n"
        "- rate_note: Rate one of the available community notes on helpfulness\n"
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
        "- rate_note: Rate an existing community note\n"
        "- pass_turn: Do nothing this turn\n\n"
        "Choose the most appropriate action based on the available "
        "requests and notes. Always explain your reasoning."
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
async def write_note(
    ctx: RunContext[SimAgentDeps],
    request_id: str,
    summary: str,
    classification: str,
) -> str:
    """Write a new community note for a request. Use this when you see a request
    that needs context or fact-checking. Classification must be one of:
    NOT_MISLEADING or MISINFORMED_OR_POTENTIALLY_MISLEADING."""
    valid_ids = {str(r["request_id"]) for r in ctx.deps.available_requests}
    if request_id not in valid_ids:
        return f"Error: request_id '{request_id}' not found in available requests."

    valid_classifications = {"NOT_MISLEADING", "MISINFORMED_OR_POTENTIALLY_MISLEADING"}
    if classification not in valid_classifications:
        return (
            f"Error: classification '{classification}' is invalid. "
            f"Must be one of: {', '.join(sorted(valid_classifications))}"
        )

    note = Note(
        request_id=request_id,
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
        logger.exception("Integrity error creating note for request %s", request_id)
        return "Error: could not create note due to a constraint violation."
    except SQLAlchemyError:
        logger.exception("Database error creating note for request %s", request_id)
        return "Error: could not create note due to a database error."

    return f"Note created for request '{request_id}' with classification '{classification}'."


@sim_agent.tool
async def rate_note(
    ctx: RunContext[SimAgentDeps],
    note_id: str,
    helpfulness_level: str,
) -> str:
    """Rate an existing community note. Use this to express whether a note is
    helpful. helpfulness_level must be one of: HELPFUL, SOMEWHAT_HELPFUL,
    NOT_HELPFUL."""
    valid_ids = {str(n["note_id"]) for n in ctx.deps.available_notes}
    if note_id not in valid_ids:
        return f"Error: note_id '{note_id}' not found in available notes."

    valid_levels = {"HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"}
    if helpfulness_level not in valid_levels:
        return (
            f"Error: helpfulness_level '{helpfulness_level}' is invalid. "
            f"Must be one of: {', '.join(sorted(valid_levels))}"
        )

    try:
        note_uuid = UUID(note_id)
    except ValueError:
        return f"Error: note_id '{note_id}' is not a valid UUID."

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
        await ctx.deps.db.execute(stmt)
        await ctx.deps.db.flush()
    except IntegrityError:
        logger.exception("Integrity error creating rating for note %s", note_id)
        return "Error: could not create rating due to a constraint violation."
    except SQLAlchemyError:
        logger.exception("Database error creating rating for note %s", note_id)
        return "Error: could not create rating due to a database error."

    return f"Rated note '{note_id}' as '{helpfulness_level}'."


@sim_agent.tool_plain
def pass_turn() -> str:
    """Do nothing this turn. Use this when no action seems appropriate
    given the current context."""
    return "Turn passed. No action taken."


@sim_agent.tool
async def post_to_channel(
    ctx: RunContext[SimAgentDeps],
    message: str,
) -> str:
    """Post a message to the shared agent channel. Use this to share research
    findings, flag patterns, express uncertainty, or coordinate with other agents."""
    if ctx.deps.simulation_run_id is None:
        return "Error: channel not available (no simulation_run_id)."

    if len(message) > MAX_CHANNEL_MESSAGE_LENGTH:
        return (
            f"Error: message too long ({len(message)} chars). "
            f"Maximum is {MAX_CHANNEL_MESSAGE_LENGTH} characters."
        )

    msg = SimChannelMessage(
        simulation_run_id=ctx.deps.simulation_run_id,
        agent_instance_id=ctx.deps.agent_instance_id,
        message_text=message,
    )
    ctx.deps.db.add(msg)
    try:
        await ctx.deps.db.flush()
    except SQLAlchemyError:
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
    result = await ctx.deps.db.execute(query)
    messages = result.scalars().all()

    if not messages:
        return "No channel messages yet."

    lines = []
    for msg in reversed(messages):
        short_id = str(msg.agent_instance_id)[:8]
        lines.append(f"[Agent {short_id}]: {msg.message_text}")
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

        result = await self._action_selector.run(
            prompt,
            deps=deps,
            message_history=message_history,
            model=self._model.to_pydantic_ai(),
        )

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
                message_history=message_history,
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
                message_history=message_history,
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
            "usage_limits": usage_limits or UsageLimits(request_limit=3, total_tokens_limit=4000),
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
                "Choose an action: write a note, rate a note, or pass.",
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
                "Choose an action: write a note, rate a note, or pass.",
                "Rate one of the notes above.",
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
        parts.append(f"\nAvailable work:\n{queue_summary}")
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
                    f"- Request ID: {req['request_id']}\n"
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
        sections.append("\nChoose an action: write a note, rate a note, or pass.")
        return "\n".join(sections)


__all__ = [
    "MAX_CHANNEL_MESSAGE_LENGTH",
    "MAX_CONTEXT_NOTES",
    "MAX_CONTEXT_REQUESTS",
    "MAX_LINKED_NOTES_PER_REQUEST",
    "MAX_PERSONALITY_CHARS",
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
    "post_to_channel",
    "read_channel",
    "sim_agent",
]
