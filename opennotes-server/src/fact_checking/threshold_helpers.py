"""Helper functions for resolving previously seen thresholds."""

from src.config import settings
from src.fact_checking.monitored_channel_models import MonitoredChannel


def get_previously_seen_thresholds(
    monitored_channel: MonitoredChannel | None,
) -> tuple[float, float]:
    """
    Resolve previously seen thresholds for a monitored channel.

    Uses channel-specific overrides if set, otherwise falls back to global config defaults.

    Args:
        monitored_channel: MonitoredChannel instance (can be None)

    Returns:
        Tuple of (autopublish_threshold, autorequest_threshold)
        - autopublish_threshold: Similarity score >= this triggers auto-publish of existing note
        - autorequest_threshold: Similarity score >= this triggers auto-request for new note
    """
    if monitored_channel is None:
        return (
            settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD,
            settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD,
        )

    # Use channel override if set (not NULL), else use config default
    autopublish_threshold = (
        monitored_channel.previously_seen_autopublish_threshold
        if monitored_channel.previously_seen_autopublish_threshold is not None
        else settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD
    )

    autorequest_threshold = (
        monitored_channel.previously_seen_autorequest_threshold
        if monitored_channel.previously_seen_autorequest_threshold is not None
        else settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD
    )

    return (autopublish_threshold, autorequest_threshold)
