"""Prompt optimization module using DSPy for vibecheck relevance checking."""

from src.vibecheck.prompt_optimization.dataset import RelevanceExample, load_training_examples
from src.vibecheck.prompt_optimization.evaluate import evaluate_model, relevance_metric
from src.vibecheck.prompt_optimization.optimize import optimize_relevance_module
from src.vibecheck.prompt_optimization.signature import RelevanceCheck

__all__ = [
    "RelevanceCheck",
    "RelevanceExample",
    "evaluate_model",
    "load_training_examples",
    "optimize_relevance_module",
    "relevance_metric",
]
