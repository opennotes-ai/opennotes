from dataclasses import dataclass
from uuid import UUID

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.notes.models import Note, Rating
from src.simulation.schemas import SimAgentAction


@dataclass
class SimAgentDeps:
    db: AsyncSession
    community_server_id: UUID
    agent_instance_id: UUID
    user_profile_id: UUID
    available_requests: list[dict]
    available_notes: list[dict]
    agent_personality: str
    model_name: str


sim_agent: Agent[SimAgentDeps, SimAgentAction] = Agent(
    deps_type=SimAgentDeps,
    output_type=SimAgentAction,
)


@sim_agent.instructions
def build_instructions(ctx: RunContext[SimAgentDeps]) -> str:
    return (
        "You are a Community Notes participant in a simulation. "
        "Your goal is to evaluate content and contribute helpful, "
        "accurate community notes.\n\n"
        f"Your personality and approach:\n{ctx.deps.agent_personality}\n\n"
        "Available actions:\n"
        "- write_note: Write a new community note for a request\n"
        "- rate_note: Rate an existing community note\n"
        "- pass_turn: Do nothing this turn\n\n"
        "Choose the most appropriate action based on the available "
        "requests and notes. Always explain your reasoning."
    )


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

    try:
        UUID(request_id)
    except ValueError:
        return f"Error: request_id '{request_id}' is not a valid UUID."

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
        ai_provider=ctx.deps.model_name,
    )
    ctx.deps.db.add(note)
    try:
        await ctx.deps.db.flush()
    except IntegrityError as e:
        return f"Error: database integrity error creating note: {e}"
    except SQLAlchemyError as e:
        return f"Error: database error creating note: {e}"

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
    except IntegrityError as e:
        return f"Error: database integrity error creating rating: {e}"
    except SQLAlchemyError as e:
        return f"Error: database error creating rating: {e}"

    return f"Rated note '{note_id}' as '{helpfulness_level}'."


@sim_agent.tool_plain
def pass_turn() -> str:
    """Do nothing this turn. Use this when no action seems appropriate
    given the current context."""
    return "Turn passed. No action taken."


class OpenNotesSimAgent:
    def __init__(self, model: str = "openai:gpt-4o-mini"):
        self._agent = sim_agent
        self._model = model

    async def run_turn(
        self,
        deps: SimAgentDeps,
        message_history: list[ModelMessage] | None = None,
        usage_limits: UsageLimits | None = None,
    ) -> tuple[SimAgentAction, list[ModelMessage]]:
        prompt = self._build_turn_prompt(deps)
        result = await self._agent.run(
            prompt,
            deps=deps,
            message_history=message_history,
            model=self._model,
            usage_limits=usage_limits or UsageLimits(request_limit=3, total_tokens_limit=4000),
        )
        return result.output, result.all_messages()

    def _build_turn_prompt(self, deps: SimAgentDeps) -> str:
        sections = ["Here is the current state of the community:\n"]

        if deps.available_requests:
            sections.append("== Available Requests ==")
            for req in deps.available_requests:
                sections.append(
                    f"- Request ID: {req['request_id']}\n"
                    f"  Content: {req.get('content', 'N/A')}\n"
                    f"  Status: {req.get('status', 'N/A')}"
                )
        else:
            sections.append("== No requests available ==")

        sections.append("")

        if deps.available_notes:
            sections.append("== Existing Notes ==")
            for note in deps.available_notes:
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
    "OpenNotesSimAgent",
    "SimAgentDeps",
    "sim_agent",
]
