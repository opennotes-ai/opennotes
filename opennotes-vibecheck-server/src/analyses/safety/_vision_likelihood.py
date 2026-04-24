from typing import Literal

VisionLikelihood = Literal[
    "UNKNOWN", "VERY_UNLIKELY", "UNLIKELY", "POSSIBLE", "LIKELY", "VERY_LIKELY"
]

_SCORE_MAP: dict[str, float] = {
    "UNKNOWN": 0.5,
    "VERY_UNLIKELY": 0.0,
    "UNLIKELY": 0.25,
    "POSSIBLE": 0.5,
    "LIKELY": 0.75,
    "VERY_LIKELY": 1.0,
}


def likelihood_to_score(level: str) -> float:
    """Map a Vision SafeSearch likelihood enum to [0.0, 1.0]."""
    return _SCORE_MAP.get(level.upper(), 0.0)
