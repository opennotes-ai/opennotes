from __future__ import annotations

import numpy as np

from opennotes_cli.analysis.correlation import (
    ClusterInfo,
    CorrelationResult,
    RaterVector,
    compute_correlation_matrix,
)


class TestRaterVector:
    def test_vector_property(self):
        rv = RaterVector(name="Agent_A", intercept=0.5, factor1=-0.3)
        vec = rv.vector
        assert isinstance(vec, np.ndarray)
        assert len(vec) == 2
        assert vec[0] == 0.5
        assert vec[1] == -0.3


class TestComputeCorrelationMatrix:
    def _make_factors(self, agents: list[tuple[str, float, float]]) -> list[dict]:
        return [
            {"agent_name": name, "intercept": intercept, "factor1": factor1}
            for name, intercept, factor1 in agents
        ]

    def test_basic_correlation(self):
        factors = self._make_factors([
            ("Alpha", 0.5, 0.3),
            ("Beta", 0.5, 0.3),
            ("Gamma", -0.5, -0.3),
        ])
        result = compute_correlation_matrix(factors)
        assert isinstance(result, CorrelationResult)
        assert len(result.labels) == 3
        assert result.similarity_matrix.shape == (3, 3)

    def test_identical_agents_have_similarity_one(self):
        factors = self._make_factors([
            ("A", 1.0, 0.5),
            ("B", 1.0, 0.5),
            ("C", 0.0, -1.0),
        ])
        result = compute_correlation_matrix(factors)
        assert result.similarity_matrix[0, 1] > 0.99

    def test_opposite_agents_have_low_similarity(self):
        factors = self._make_factors([
            ("A", 1.0, 1.0),
            ("B", -1.0, -1.0),
            ("C", 0.5, 0.5),
        ])
        result = compute_correlation_matrix(factors)
        assert result.similarity_matrix[0, 1] < 0.0

    def test_clusters_are_produced(self):
        factors = self._make_factors([
            ("A", 1.0, 1.0),
            ("B", 0.9, 0.95),
            ("C", -1.0, -1.0),
            ("D", -0.9, -0.95),
        ])
        result = compute_correlation_matrix(factors)
        assert len(result.clusters) >= 1
        for c in result.clusters:
            assert isinstance(c, ClusterInfo)
            assert len(c.members) >= 1

    def test_most_similar_and_different_pairs(self):
        factors = self._make_factors([
            ("A", 1.0, 1.0),
            ("B", 0.99, 0.99),
            ("C", -1.0, -1.0),
        ])
        result = compute_correlation_matrix(factors)
        assert len(result.most_similar_pairs) > 0
        assert len(result.most_different_pairs) > 0
        assert result.most_similar_pairs[0][2] >= result.most_different_pairs[0][2]

    def test_labels_match_agent_names(self):
        factors = self._make_factors([
            ("Alpha", 0.1, 0.2),
            ("Beta", 0.3, 0.4),
            ("Gamma", 0.5, 0.6),
        ])
        result = compute_correlation_matrix(factors)
        assert result.labels == ["Alpha", "Beta", "Gamma"]

    def test_falls_back_to_rater_id(self):
        factors = [
            {"rater_id": "uuid-1", "intercept": 0.1, "factor1": 0.2},
            {"rater_id": "uuid-2", "intercept": 0.3, "factor1": 0.4},
            {"rater_id": "uuid-3", "intercept": 0.5, "factor1": 0.6},
        ]
        result = compute_correlation_matrix(factors)
        assert result.labels == ["uuid-1", "uuid-2", "uuid-3"]
