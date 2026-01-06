"""Tests for prompt optimization module."""


from src.vibecheck.prompt_optimization.dataset import (
    TRAINING_EXAMPLES,
    RelevanceExample,
    get_train_test_split,
    load_training_examples,
)
from src.vibecheck.prompt_optimization.evaluate import (
    precision_at_k,
    recall_at_k,
    relevance_metric,
)
from src.vibecheck.prompt_optimization.prompts import (
    OPTIMIZED_SYSTEM_PROMPT,
    OPTIMIZED_USER_PROMPT_TEMPLATE,
    get_optimized_prompts,
)
from src.vibecheck.prompt_optimization.signature import RelevanceCheck


class TestDataset:
    """Tests for dataset module."""

    def test_training_examples_count(self):
        """Should have at least 10 training examples."""
        assert len(TRAINING_EXAMPLES) >= 10

    def test_training_examples_balance(self):
        """Should have balanced positive and negative examples."""
        positive = sum(1 for ex in TRAINING_EXAMPLES if ex.is_relevant)
        negative = len(TRAINING_EXAMPLES) - positive
        assert positive >= 4, "Need at least 4 positive examples"
        assert negative >= 4, "Need at least 4 negative examples"

    def test_load_training_examples(self):
        """Should load all examples as DSPy Examples."""
        examples = load_training_examples()
        assert len(examples) == len(TRAINING_EXAMPLES)
        for ex in examples:
            assert hasattr(ex, "message")
            assert hasattr(ex, "fact_check_title")
            assert hasattr(ex, "fact_check_content")
            assert hasattr(ex, "is_relevant")
            assert hasattr(ex, "reasoning")

    def test_train_test_split(self):
        """Should split examples into train and test sets."""
        train, test = get_train_test_split(test_ratio=0.2)
        total = len(train) + len(test)
        assert total == len(TRAINING_EXAMPLES)
        assert len(test) >= 1

    def test_relevance_example_to_dspy(self):
        """Should convert RelevanceExample to DSPy Example correctly."""
        ex = RelevanceExample(
            example_id="test-001",
            message="test message",
            fact_check_title="Test Title",
            fact_check_content="Test content",
            is_relevant=True,
            reasoning="Test reasoning",
        )
        dspy_ex = ex.to_dspy_example()
        assert dspy_ex.message == "test message"
        assert dspy_ex.is_relevant is True


class TestEvaluationMetrics:
    """Tests for evaluation metrics."""

    def test_relevance_metric_correct_positive(self):
        """Should return 1.0 for correct positive prediction."""

        class MockExample:
            is_relevant = True

        class MockPrediction:
            is_relevant = True

        score = relevance_metric(MockExample(), MockPrediction())
        assert score == 1.0

    def test_relevance_metric_correct_negative(self):
        """Should return 1.0 for correct negative prediction."""

        class MockExample:
            is_relevant = False

        class MockPrediction:
            is_relevant = False

        score = relevance_metric(MockExample(), MockPrediction())
        assert score == 1.0

    def test_relevance_metric_false_positive(self):
        """Should return 0.0 for false positive (heavily penalized)."""

        class MockExample:
            is_relevant = False

        class MockPrediction:
            is_relevant = True

        score = relevance_metric(MockExample(), MockPrediction())
        assert score == 0.0

    def test_relevance_metric_false_negative(self):
        """Should return 0.3 for false negative (less severe)."""

        class MockExample:
            is_relevant = True

        class MockPrediction:
            is_relevant = False

        score = relevance_metric(MockExample(), MockPrediction())
        assert score == 0.3

    def test_precision_all_correct(self):
        """Should return 1.0 when all positives are correct."""

        class Ex:
            def __init__(self, rel):
                self.is_relevant = rel

        class Pred:
            def __init__(self, rel):
                self.is_relevant = rel

        examples = [Ex(True), Ex(True), Ex(False)]
        predictions = [Pred(True), Pred(True), Pred(False)]
        assert precision_at_k(examples, predictions) == 1.0

    def test_recall_all_correct(self):
        """Should return 1.0 when all true positives are found."""

        class Ex:
            def __init__(self, rel):
                self.is_relevant = rel

        class Pred:
            def __init__(self, rel):
                self.is_relevant = rel

        examples = [Ex(True), Ex(True), Ex(False)]
        predictions = [Pred(True), Pred(True), Pred(False)]
        assert recall_at_k(examples, predictions) == 1.0


class TestOptimizedPrompts:
    """Tests for optimized prompts."""

    def test_system_prompt_contains_few_shot_examples(self):
        """Optimized system prompt should contain few-shot examples."""
        assert "Example 1" in OPTIMIZED_SYSTEM_PROMPT
        assert "Example 2" in OPTIMIZED_SYSTEM_PROMPT
        assert "NOT RELEVANT" in OPTIMIZED_SYSTEM_PROMPT
        assert "RELEVANT" in OPTIMIZED_SYSTEM_PROMPT

    def test_system_prompt_emphasizes_claim_detection(self):
        """System prompt should emphasize claim detection."""
        assert "SPECIFIC CLAIM" in OPTIMIZED_SYSTEM_PROMPT
        assert "verifiable" in OPTIMIZED_SYSTEM_PROMPT.lower()
        assert "topic mention" in OPTIMIZED_SYSTEM_PROMPT.lower()

    def test_user_prompt_template_has_placeholders(self):
        """User prompt template should have required placeholders."""
        assert "{message}" in OPTIMIZED_USER_PROMPT_TEMPLATE
        assert "{fact_check_title}" in OPTIMIZED_USER_PROMPT_TEMPLATE
        assert "{fact_check_content}" in OPTIMIZED_USER_PROMPT_TEMPLATE

    def test_get_optimized_prompts(self):
        """Should generate prompts with filled placeholders."""
        system, user = get_optimized_prompts(
            message="test message",
            fact_check_title="Test Title",
            fact_check_content="Test content",
        )
        assert "test message" in user
        assert "Test Title" in user
        assert "Test content" in user
        assert system == OPTIMIZED_SYSTEM_PROMPT

    def test_get_optimized_prompts_with_source(self):
        """Should include source URL when provided."""
        _system, user = get_optimized_prompts(
            message="test",
            fact_check_title="Title",
            fact_check_content="Content",
            source_url="https://example.com",
        )
        assert "https://example.com" in user


class TestSignature:
    """Tests for DSPy signature."""

    def test_signature_has_required_fields(self):
        """Signature should have all required input/output fields."""
        fields = RelevanceCheck.model_fields
        assert "message" in fields
        assert "fact_check_title" in fields
        assert "fact_check_content" in fields
        assert "is_relevant" in fields
        assert "reasoning" in fields

    def test_signature_docstring_emphasizes_claims(self):
        """Signature docstring should emphasize claim detection."""
        assert RelevanceCheck.__doc__ is not None
        assert "claim" in RelevanceCheck.__doc__.lower()
        assert "verifiable" in RelevanceCheck.__doc__.lower()
