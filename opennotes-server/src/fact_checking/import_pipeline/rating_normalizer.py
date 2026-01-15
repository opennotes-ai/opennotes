"""Rating normalization for fact-check verdicts.

Maps various rating formats from different sources to canonical lowercase
snake_case values for consistent storage and querying.

Canonical ratings (10 total):
- false, true, mostly_false, mostly_true, mixture
- unproven, misleading, satire, legend, outdated

Intermediate values are mapped to canonical ratings, with the original
stored in rating_details for context preservation.
"""

import logging

logger = logging.getLogger(__name__)

CANONICAL_RATINGS: set[str] = {
    "false",
    "true",
    "mostly_false",
    "mostly_true",
    "mixture",
    "unproven",
    "misleading",
    "satire",
    "legend",
    "outdated",
}

INTERMEDIATE_TO_CANONICAL: dict[str, str] = {
    "missing_context": "misleading",
    "altered": "false",
    "miscaptioned": "false",
    "misattributed": "false",
    "correct_attribution": "true",
    "scam": "false",
    "out_of_context": "misleading",
    "exaggerated": "misleading",
}

SKIP_RATINGS: set[str] = {"in_progress", "explainer", "flip", "recall"}

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
    # -------------------------------------------------------------------
    # French verdicts
    # -------------------------------------------------------------------
    "Faux": "false",
    "faux": "false",
    "FAUX": "false",
    "Vrai": "true",
    "vrai": "true",
    "VRAI": "true",
    "Trompeur": "misleading",
    "trompeur": "misleading",
    "TROMPEUR": "misleading",
    "Plutôt Vrai": "mostly_true",
    "plutôt vrai": "mostly_true",
    "Plutôt vrai": "mostly_true",
    "Plutôt Faux": "mostly_false",
    "plutôt faux": "mostly_false",
    "Plutôt faux": "mostly_false",
    "C'est plus compliqué": "mixture",
    "c'est plus compliqué": "mixture",
    "Partiellement faux": "mixture",
    "partiellement faux": "mixture",
    "Partiellement vrai": "mixture",
    "partiellement vrai": "mixture",
    "Contexte manquant": "missing_context",
    "contexte manquant": "missing_context",
    "Infondé": "unproven",
    "infondé": "unproven",
    "Montage": "altered",
    "montage": "altered",
    "Photomontage": "altered",
    "photomontage": "altered",
    "Manipulé": "altered",
    "manipulé": "altered",
    "Détourné": "out_of_context",
    "détourné": "out_of_context",
    "Hors contexte": "out_of_context",
    "hors contexte": "out_of_context",
    "Exagéré": "exaggerated",
    "exagéré": "exaggerated",
    "À vérifier": "in_progress",
    "à vérifier": "in_progress",
    "Arnaque": "scam",
    "arnaque": "scam",
    # -------------------------------------------------------------------
    # Spanish verdicts
    # -------------------------------------------------------------------
    "Falso": "false",
    "falso": "false",
    "FALSO": "false",
    "Verdadero": "true",
    "verdadero": "true",
    "VERDADERO": "true",
    "Engañoso": "misleading",
    "engañoso": "misleading",
    "Parcialmente falso": "mostly_false",
    "parcialmente falso": "mostly_false",
    "Parcialmente verdadero": "mostly_true",
    "parcialmente verdadero": "mostly_true",
    "Sin contexto": "missing_context",
    "sin contexto": "missing_context",
    "Sin pruebas": "unproven",
    "sin pruebas": "unproven",
    "Sátira": "satire",
    "sátira": "satire",
    "Estafa": "scam",
    "estafa": "scam",
    # -------------------------------------------------------------------
    # German verdicts
    # -------------------------------------------------------------------
    "Falsch": "false",
    "falsch": "false",
    "FALSCH": "false",
    "Wahr": "true",
    "wahr": "true",
    "WAHR": "true",
    "Irreführend": "misleading",
    "irreführend": "misleading",
    "Teilweise falsch": "mostly_false",
    "teilweise falsch": "mostly_false",
    "Teilweise wahr": "mostly_true",
    "teilweise wahr": "mostly_true",
    "Unbelegt": "unproven",
    "unbelegt": "unproven",
    "Manipuliert": "altered",
    "manipuliert": "altered",
    "Fehlender Kontext": "missing_context",
    "fehlender Kontext": "missing_context",
    # -------------------------------------------------------------------
    # Portuguese verdicts (note: "Falso" shared with Spanish)
    # -------------------------------------------------------------------
    "Verdadeiro": "true",
    "verdadeiro": "true",
    "Enganoso": "misleading",
    "enganoso": "misleading",
    "Parcialmente verdadeiro": "mostly_true",
    "parcialmente verdadeiro": "mostly_true",
    "Sem provas": "unproven",
    "sem provas": "unproven",
    "Fora de contexto": "out_of_context",
    "fora de contexto": "out_of_context",
    # -------------------------------------------------------------------
    # Italian verdicts (note: "Falso" shared with Spanish/Portuguese)
    # -------------------------------------------------------------------
    "Vero": "true",
    "vero": "true",
    "VERO": "true",
    "Fuorviante": "misleading",
    "fuorviante": "misleading",
    "Parzialmente falso": "mostly_false",
    "parzialmente falso": "mostly_false",
    "Parzialmente vero": "mostly_true",
    "parzialmente vero": "mostly_true",
    "Senza prove": "unproven",
    "senza prove": "unproven",
    "Satira": "satire",
    "Nessuna prova": "unproven",
    "nessuna prova": "unproven",
    # -------------------------------------------------------------------
    # Dutch verdicts
    # -------------------------------------------------------------------
    "Vals": "false",
    "vals": "false",
    "Waar": "true",
    "waar": "true",
    "Misleidend": "misleading",
    "misleidend": "misleading",
    "Onbewezen": "unproven",
    "onbewezen": "unproven",
    # -------------------------------------------------------------------
    # English content type verdicts (Snopes, PolitiFact, etc.)
    # -------------------------------------------------------------------
    # Missing context
    "Missing Context": "missing_context",
    "missing context": "missing_context",
    "Missing context": "missing_context",
    "Needs Context": "missing_context",
    "needs context": "missing_context",
    "Lacks Context": "missing_context",
    "lacks context": "missing_context",
    "No Context": "missing_context",
    "no context": "missing_context",
    # Altered/manipulated content
    "Altered": "altered",
    "altered": "altered",
    "ALTERED": "altered",
    "Digitally Altered": "altered",
    "digitally altered": "altered",
    "Photo Altered": "altered",
    "photo altered": "altered",
    "Manipulated": "altered",
    "manipulated": "altered",
    "Doctored": "altered",
    "doctored": "altered",
    "Edited": "altered",
    "edited": "altered",
    # Miscaptioned
    "Miscaptioned": "miscaptioned",
    "miscaptioned": "miscaptioned",
    "MISCAPTIONED": "miscaptioned",
    "Wrong Caption": "miscaptioned",
    "wrong caption": "miscaptioned",
    "Caption False": "miscaptioned",
    "caption false": "miscaptioned",
    # Misattributed
    "Misattributed": "misattributed",
    "misattributed": "misattributed",
    "MISATTRIBUTED": "misattributed",
    "Wrong Attribution": "misattributed",
    "wrong attribution": "misattributed",
    "Wrongly Attributed": "misattributed",
    "wrongly attributed": "misattributed",
    # Correct attribution
    "Correct Attribution": "correct_attribution",
    "correct attribution": "correct_attribution",
    "Correctly Attributed": "correct_attribution",
    "correctly attributed": "correct_attribution",
    # Satire variants
    "Labeled Satire": "satire",
    "labeled satire": "satire",
    "LABELED SATIRE": "satire",
    "Originated as Satire": "satire",
    "originated as satire": "satire",
    "Originated As Satire": "satire",
    "Satirical": "satire",
    "satirical": "satire",
    # Scam
    "Scam": "scam",
    "scam": "scam",
    "SCAM": "scam",
    "Fraud": "scam",
    "fraud": "scam",
    "Fraudulent": "scam",
    "fraudulent": "scam",
    # Out of context
    "Out of Context": "out_of_context",
    "out of context": "out_of_context",
    "Taken Out of Context": "out_of_context",
    "taken out of context": "out_of_context",
    # Exaggerated
    "Exaggerated": "exaggerated",
    "exaggerated": "exaggerated",
    "Exaggeration": "exaggerated",
    "exaggeration": "exaggerated",
    "Overblown": "exaggerated",
    "overblown": "exaggerated",
    # In progress / research
    "In Progress": "in_progress",
    "in progress": "in_progress",
    "Research In Progress": "in_progress",
    "research in progress": "in_progress",
    "Under Review": "in_progress",
    "under review": "in_progress",
    # Explainer (informational, not a verdict)
    "Explainer": "explainer",
    "explainer": "explainer",
    "Informational": "explainer",
    "informational": "explainer",
    # Political flip (PolitiFact specific)
    "Full Flop": "flip",
    "full flop": "flip",
    "Half Flip": "flip",
    "half flip": "flip",
    "No Flip": "flip",
    "no flip": "flip",
    # Product recall ratings
    "Recall": "recall",
    "recall": "recall",
    "Product Recall": "recall",
    "product recall": "recall",
    # Additional false variants
    "Fake": "false",
    "fake": "false",
    "FAKE": "false",
    "Fabricated": "false",
    "fabricated": "false",
    "Not True": "false",
    "not true": "false",
    # Additional unproven variants
    "Unfounded": "unproven",
    "unfounded": "unproven",
    "Unsubstantiated": "unproven",
    "unsubstantiated": "unproven",
    "No Evidence": "unproven",
    "no evidence": "unproven",
    "Insufficient Evidence": "unproven",
    "insufficient evidence": "unproven",
}


def normalize_rating(rating: str | None) -> tuple[str | None, str | None]:
    """Normalize a fact-check rating to canonical format.

    Maps ratings to one of 10 canonical values, storing the original
    rating in rating_details when normalization occurs.

    Args:
        rating: The raw rating string from the source dataset.

    Returns:
        Tuple of (canonical_rating, rating_details):
        - canonical_rating: One of the 10 canonical ratings, or None for skipped/empty
        - rating_details: Original rating value if different from canonical, None otherwise

    Canonical ratings: false, true, mostly_false, mostly_true, mixture,
                       unproven, misleading, satire, legend, outdated

    Skipped ratings (return None): in_progress, explainer, flip, recall

    Examples:
        >>> normalize_rating("False")
        ('false', None)
        >>> normalize_rating("Mostly True")
        ('mostly_true', None)
        >>> normalize_rating("Missing Context")
        ('misleading', 'missing_context')
        >>> normalize_rating("Altered")
        ('false', 'altered')
        >>> normalize_rating("In Progress")
        (None, 'in_progress')
        >>> normalize_rating("Unknown Rating")
        ('unknown_rating', 'Unknown Rating')
    """
    if not rating or not rating.strip():
        return (None, None)

    rating_stripped = rating.strip()

    if rating_stripped in RATING_MAPPINGS:
        intermediate = RATING_MAPPINGS[rating_stripped]
        return _resolve_intermediate(intermediate)

    normalized = rating_stripped.lower().replace(" ", "_").replace("-", "_")
    result = _resolve_intermediate(normalized)

    if result[0] is not None or result[1] is not None:
        return result

    logger.warning(f"Unknown rating value: '{rating}' -> '{normalized}'")
    return (normalized, rating_stripped)


def _resolve_intermediate(intermediate: str) -> tuple[str | None, str | None]:
    """Resolve an intermediate rating value to canonical form.

    Args:
        intermediate: A normalized/intermediate rating string.

    Returns:
        Tuple of (canonical_rating, rating_details).
    """
    if intermediate in SKIP_RATINGS:
        return (None, intermediate)

    if intermediate in INTERMEDIATE_TO_CANONICAL:
        canonical = INTERMEDIATE_TO_CANONICAL[intermediate]
        return (canonical, intermediate)

    if intermediate in CANONICAL_RATINGS:
        return (intermediate, None)

    return (None, None)
