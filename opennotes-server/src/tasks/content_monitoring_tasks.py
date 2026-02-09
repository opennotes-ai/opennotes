"""
TaskIQ tasks for content monitoring operations.

DEPRECATED: AI note generation, vision description, and audit log tasks have been
migrated to DBOS durable workflows. See src/dbos_workflows/content_monitoring_workflows.py.

The @register_task stubs below exist solely to drain legacy JetStream messages that
may still be in-flight. They return {"status": "deprecated"} immediately.

Helper functions (_create_db_engine, _get_llm_service, _build_fact_check_prompt,
_build_general_explanation_prompt) are retained because they are imported by DBOS
workflow steps and by content_scan_workflow.py.
"""

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import create_async_engine

from src.tasks.broker import register_task

if TYPE_CHECKING:
    from src.fact_checking.models import FactCheckItem

logger = logging.getLogger(__name__)


def _create_db_engine(db_url: str) -> Any:
    """Create async database engine with pool settings."""
    from src.config import get_settings

    settings = get_settings()
    return create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )


def _get_llm_service() -> Any:
    """Create LLMService with required dependencies."""
    from src.config import get_settings
    from src.llm_config.encryption import EncryptionService
    from src.llm_config.manager import LLMClientManager
    from src.llm_config.service import LLMService

    settings = get_settings()
    llm_client_manager = LLMClientManager(
        encryption_service=EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    )
    return LLMService(client_manager=llm_client_manager)


@register_task(task_name="content:ai_note", component="content_monitoring", task_type="generation")
async def generate_ai_note_task(
    community_server_id: str,
    request_id: str,
    content: str,
    scan_type: str,
    db_url: str,
    fact_check_item_id: str | None = None,
    similarity_score: float | None = None,
    moderation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deprecated: TaskIQ stub to drain legacy JetStream messages.
    AI note generation has been migrated to DBOS workflows.
    See src/dbos_workflows/content_monitoring_workflows.py
    """
    logger.info("Deprecated TaskIQ stub: content:ai_note (draining legacy message)")
    return {"status": "deprecated", "migrated_to": "dbos"}


def _build_fact_check_prompt(
    original_message: str,
    fact_check_item: "FactCheckItem",
    similarity_score: float,
) -> str:
    """Build prompt for fact-check note generation."""
    return f"""Original Message:
{original_message}

Fact-Check Information:
Title: {fact_check_item.title}
Rating: {fact_check_item.rating}
Summary: {fact_check_item.summary}
Content: {fact_check_item.content}
Source: {fact_check_item.source_url}

Match Confidence: {similarity_score:.2%}

Please write a concise, informative community note that:
1. Addresses the claim in the original message
2. Provides context from the fact-check information
3. Maintains a neutral, factual tone
4. Is clear and easy to understand
5. Is no more than 280 characters if possible

Community Note:"""


def _build_general_explanation_prompt(
    original_message: str,
    moderation_metadata: dict[str, Any] | None = None,
) -> str:
    """Build prompt for general explanation note generation.

    Args:
        original_message: Original message content
        moderation_metadata: Optional OpenAI moderation results containing:
            - categories: dict of category name to bool (whether flagged)
            - scores: dict of category name to float (confidence score 0-1)
            - flagged_categories: list of category names that were flagged

    Returns:
        Formatted prompt for LLM
    """
    prompt_parts = [f"Original Message:\n{original_message}"]

    if moderation_metadata:
        moderation_context = "\nContent Moderation Analysis:"
        flagged_categories = moderation_metadata.get("flagged_categories", [])
        scores = moderation_metadata.get("scores", {})

        if flagged_categories:
            moderation_context += f"\nFlagged Categories: {', '.join(flagged_categories)}"
            relevant_scores = {
                cat: f"{score:.2%}" for cat, score in scores.items() if cat in flagged_categories
            }
            if relevant_scores:
                moderation_context += f"\nConfidence Scores: {relevant_scores}"

        prompt_parts.append(moderation_context)

    prompt_parts.append("""
Please analyze this content and write a concise, informative community note that:
1. Explains the message content
2. Provides helpful context and clarification
3. Addresses any potential misunderstandings
4. Maintains a neutral, factual tone
5. Is clear and easy to understand
6. Is no more than 280 characters if possible

Focus on helping readers understand what the content is about, what context might be important, and any relevant information that would be helpful to know.

Community Note:""")

    return "\n".join(prompt_parts)


@register_task(
    task_name="content:vision_description", component="content_monitoring", task_type="vision"
)
async def process_vision_description_task(
    message_archive_id: str,
    image_url: str,
    community_server_id: str,
    db_url: str,
) -> dict[str, Any]:
    """Deprecated: TaskIQ stub to drain legacy JetStream messages.
    Vision description has been migrated to DBOS workflows.
    See src/dbos_workflows/content_monitoring_workflows.py
    """
    logger.info("Deprecated TaskIQ stub: content:vision_description (draining legacy message)")
    return {"status": "deprecated", "migrated_to": "dbos"}


@register_task(task_name="content:audit_log", component="content_monitoring", task_type="audit")
async def persist_audit_log_task(
    user_id: str | None,
    community_server_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None,
    details: dict[str, Any] | None,
    ip_address: str | None,
    user_agent: str | None,
    db_url: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Deprecated: TaskIQ stub to drain legacy JetStream messages.
    Audit log persistence has been migrated to DBOS workflows.
    See src/dbos_workflows/content_monitoring_workflows.py
    """
    logger.info("Deprecated TaskIQ stub: content:audit_log (draining legacy message)")
    return {"status": "deprecated", "migrated_to": "dbos"}
