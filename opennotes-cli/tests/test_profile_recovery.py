from __future__ import annotations

from opennotes_cli.analysis.profile_recovery import (
    ASSIGNMENT_MATRIX,
    DIMENSIONS,
    ProfileRecoveryResult,
    compute_profile_recovery,
)


class TestAssignmentMatrix:
    def test_has_20_agents(self):
        assert len(ASSIGNMENT_MATRIX) == 20

    def test_each_agent_has_12_dimensions(self):
        for name, dims in ASSIGNMENT_MATRIX.items():
            assert len(dims) == 12, f"{name} has {len(dims)} dimensions"

    def test_all_dimensions_present(self):
        for name, dims in ASSIGNMENT_MATRIX.items():
            for dim in DIMENSIONS:
                assert dim in dims, f"{name} missing dimension {dim}"

    def test_known_agents(self):
        assert "Mara" in ASSIGNMENT_MATRIX
        assert "Dex" in ASSIGNMENT_MATRIX
        assert "Zara" in ASSIGNMENT_MATRIX

    def test_mara_dimensions(self):
        mara = ASSIGNMENT_MATRIX["Mara"]
        assert mara["D-I"] == "Addressee"
        assert mara["D-II.A"] == "Analyst"
        assert mara["E-II"] == "Calibrator"


class TestComputeProfileRecovery:
    def _make_factors(self, agents: list[tuple[str, float, float]]) -> list[dict]:
        return [
            {"agent_name": name, "intercept": intercept, "factor1": factor1}
            for name, intercept, factor1 in agents
        ]

    def test_insufficient_agents(self):
        factors = self._make_factors([("Mara", 0.5, 0.3)])
        result = compute_profile_recovery(factors)
        assert isinstance(result, ProfileRecoveryResult)
        assert result.n_agents_matched == 1
        assert len(result.agent_comparisons) == 0

    def test_unmatched_agents(self):
        factors = self._make_factors([
            ("Unknown1", 0.5, 0.3),
            ("Unknown2", -0.5, -0.3),
            ("Unknown3", 0.1, 0.1),
        ])
        result = compute_profile_recovery(factors)
        assert result.n_agents_matched == 0

    def test_matched_agents_produce_comparisons(self):
        factors = self._make_factors([
            ("Mara", 0.5, 0.3),
            ("Dex", -0.5, -0.3),
            ("Sable", 0.1, 0.1),
            ("Kai", 0.4, 0.2),
        ])
        result = compute_profile_recovery(factors)
        assert result.n_agents_matched == 4
        assert len(result.agent_comparisons) == 4

    def test_correlation_is_computed(self):
        factors = self._make_factors([
            ("Mara", 0.5, 0.3),
            ("Dex", -0.5, -0.3),
            ("Sable", 0.1, 0.1),
            ("Kai", 0.4, 0.2),
        ])
        result = compute_profile_recovery(factors)
        assert -1.0 <= result.archetype_factor_correlation <= 1.0
        assert 0.0 <= result.archetype_factor_p_value <= 1.0
        assert -1.0 <= result.archetype_factor_spearman <= 1.0

    def test_comparison_has_required_fields(self):
        factors = self._make_factors([
            ("Mara", 0.5, 0.3),
            ("Dex", -0.5, -0.3),
            ("Sable", 0.1, 0.1),
        ])
        result = compute_profile_recovery(factors)
        for comp in result.agent_comparisons:
            assert "name" in comp
            assert "dimensions" in comp
            assert "intercept" in comp
            assert "factor1" in comp
            assert "closest_by_archetype" in comp
            assert "closest_by_factors" in comp
            assert "match" in comp

    def test_all_20_agents(self):
        factors = self._make_factors(
            [(name, i * 0.1, i * -0.05) for i, name in enumerate(ASSIGNMENT_MATRIX)]
        )
        result = compute_profile_recovery(factors)
        assert result.n_agents_matched == 20
        assert result.n_agents_total == 20
        assert len(result.agent_comparisons) == 20
