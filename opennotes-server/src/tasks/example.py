"""
Example tasks for testing taskiq integration.

These tasks demonstrate the taskiq task pattern and are used by integration tests
to verify the broker and result backend are working correctly.
"""

import asyncio

from src.tasks.broker import broker


@broker.task
async def example_task(message: str) -> str:
    """
    Process a message and return the result.

    Args:
        message: The input message to process

    Returns:
        The processed message with prefix "Processed: "
    """
    return f"Processed: {message}"


@broker.task
async def slow_task(delay_seconds: float) -> str:
    """
    A slow task that sleeps for a specified duration.

    Args:
        delay_seconds: Number of seconds to sleep

    Returns:
        "Done" after the delay completes
    """
    await asyncio.sleep(delay_seconds)
    return "Done"


@broker.task
async def failing_task() -> None:
    """
    A task that always fails with a ValueError.

    Used for testing error handling in task execution.

    Raises:
        ValueError: Always raises with message "Intentional failure"
    """
    raise ValueError("Intentional failure")
