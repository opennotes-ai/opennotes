"""Testing exports for trends/oppositions structured LLM output models."""
from __future__ import annotations

from src.analyses.opinions.trends_oppositions import (
    _OppositionLLM as OppositionLLMForTest,
)
from src.analyses.opinions.trends_oppositions import (
    _TrendLLM as TrendLLMForTest,
)
from src.analyses.opinions.trends_oppositions import (
    _TrendsOppositionsLLM as TrendsOppositionsLLMForTest,
)

__all__ = [
    "OppositionLLMForTest",
    "TrendLLMForTest",
    "TrendsOppositionsLLMForTest",
]
