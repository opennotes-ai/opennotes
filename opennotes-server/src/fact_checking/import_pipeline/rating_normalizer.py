"""Rating normalization for fact-check verdicts.

Maps various rating formats from different sources to canonical lowercase
snake_case values for consistent storage and querying.
"""

import logging

logger = logging.getLogger(__name__)

RATING_MAPPINGS: dict[str, str] = {
    # Boolean verdicts
    "false": "false",
    "true": "true",
    "False": "false",
    "True": "true",
    "FALSE": "false",
    "TRUE": "true",
    # Mostly verdicts
    "mostly false": "mostly_false",
    "mostly true": "mostly_true",
    "Mostly False": "mostly_false",
    "Mostly True": "mostly_true",
    "mostly-false": "mostly_false",
    "mostly-true": "mostly_true",
    # Mixed/partial verdicts
    "mixture": "mixture",
    "Mixture": "mixture",
    "mixed": "mixture",
    "Mixed": "mixture",
    "half true": "mixture",
    "Half True": "mixture",
    "partly false": "mixture",
    "Partly False": "mixture",
    "partially true": "mixture",
    "Partially True": "mixture",
    # Unverifiable
    "unproven": "unproven",
    "Unproven": "unproven",
    "unverified": "unproven",
    "Unverified": "unproven",
    "not verifiable": "unproven",
    "Not Verifiable": "unproven",
    # Misleading
    "misleading": "misleading",
    "Misleading": "misleading",
    # Satire/fake
    "satire": "satire",
    "Satire": "satire",
    "legend": "legend",
    "Legend": "legend",
    # Outdated
    "outdated": "outdated",
    "Outdated": "outdated",
    # Correct/accurate
    "correct": "true",
    "Correct": "true",
    "accurate": "true",
    "Accurate": "true",
    # Additional common variations
    "pants on fire": "false",
    "Pants on Fire": "false",
    "four pinocchios": "false",
    "Four Pinocchios": "false",
    "three pinocchios": "mostly_false",
    "Three Pinocchios": "mostly_false",
    "two pinocchios": "mixture",
    "Two Pinocchios": "mixture",
    "one pinocchio": "mostly_true",
    "One Pinocchio": "mostly_true",
}


def normalize_rating(rating: str | None) -> str | None:
    """Normalize a fact-check rating to canonical format.

    Args:
        rating: The raw rating string from the source dataset.

    Returns:
        Normalized lowercase rating string, or original value if unknown.
        Returns None if input is None or empty.

    Examples:
        >>> normalize_rating("False")
        'false'
        >>> normalize_rating("Mostly True")
        'mostly_true'
        >>> normalize_rating("Pants on Fire")
        'false'
        >>> normalize_rating("Unknown Rating")
        'unknown rating'
    """
    if not rating:
        return None

    rating_stripped = rating.strip()
    if not rating_stripped:
        return None

    if rating_stripped in RATING_MAPPINGS:
        return RATING_MAPPINGS[rating_stripped]

    normalized = rating_stripped.lower().replace(" ", "_").replace("-", "_")

    if normalized not in set(RATING_MAPPINGS.values()):
        logger.warning(f"Unknown rating value: '{rating}' -> '{normalized}'")

    return normalized
