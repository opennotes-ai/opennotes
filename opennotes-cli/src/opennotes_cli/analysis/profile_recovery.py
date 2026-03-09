from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial.distance import cosine
from scipy.stats import pearsonr, spearmanr

ASSIGNMENT_MATRIX: dict[str, dict[str, str]] = {
    "Mara": {
        "D-I": "Addressee", "D-II.A": "Analyst", "D-II.B": "Analyst",
        "D-II.C": "Stoic", "D-III": "Frame-Rider", "D-IV": "Face-Guardian",
        "D-V": "Aligner", "E-I": "Evaluativist", "E-II": "Calibrator",
        "E-III": "Empiricist", "E-IV": "Institutionalist", "E-V": "Epistemic Pragmatist",
    },
    "Dex": {
        "D-I": "Mouthpiece", "D-II.A": "Authority", "D-II.B": "Critic",
        "D-II.C": "Provocateur", "D-III": "Frame-Breaker", "D-IV": "Face-Threatener",
        "D-V": "Differentiator", "E-I": "Multiplist", "E-II": "Overclaimer",
        "E-III": "Deconstructionist", "E-IV": "Autodidact", "E-V": "Epistemic Relativist",
    },
    "Sable": {
        "D-I": "Side-Participant", "D-II.A": "Seeker", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Reframer", "D-IV": "Face-Negotiator",
        "D-V": "Narrator", "E-I": "Evaluativist", "E-II": "Underclaimer",
        "E-III": "Narrativist", "E-IV": "Experientialist", "E-V": "Epistemic Justice Advocate",
    },
    "Kai": {
        "D-I": "Addressee", "D-II.A": "Authority", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Frame-Setter", "D-IV": "Face-Guardian",
        "D-V": "Aligner", "E-I": "Evaluativist", "E-II": "Knower (K+)",
        "E-III": "Consensus-Invoker", "E-IV": "Institutionalist", "E-V": "Epistemic Egalitarian",
    },
    "Raven": {
        "D-I": "Composer", "D-II.A": "Skeptic", "D-II.B": "Critic",
        "D-II.C": "Stoic", "D-III": "Reframer", "D-IV": "Face-Threatener",
        "D-V": "Differentiator", "E-I": "Meta-Epistemologist", "E-II": "Epistemic Challenger",
        "E-III": "Deconstructionist", "E-IV": "Pluralist", "E-V": "Epistemic Justice Advocate",
    },
    "Jules": {
        "D-I": "Mouthpiece", "D-II.A": "Authority", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Frame-Rider", "D-IV": "Face-Negotiator",
        "D-V": "Narrator", "E-I": "Evaluativist", "E-II": "Underclaimer",
        "E-III": "Narrativist", "E-IV": "Experientialist", "E-V": "Epistemic Pragmatist",
    },
    "Petra": {
        "D-I": "Addressee", "D-II.A": "Authority", "D-II.B": "Analyst",
        "D-II.C": "Stoic", "D-III": "Frame-Setter", "D-IV": "Face-Ignorer",
        "D-V": "Gatekeeper", "E-I": "Evaluativist", "E-II": "Knower (K+)",
        "E-III": "Empiricist", "E-IV": "Institutionalist", "E-V": "Epistemic Gatekeeper",
    },
    "Felix": {
        "D-I": "Mouthpiece", "D-II.A": "Hedger", "D-II.B": "Analyst",
        "D-II.C": "Empathizer", "D-III": "Reframer", "D-IV": "Face-Negotiator",
        "D-V": "Performer", "E-I": "Meta-Epistemologist", "E-II": "Calibrator",
        "E-III": "Stake Manager", "E-IV": "Pluralist", "E-V": "Epistemic Egalitarian",
    },
    "Thorne": {
        "D-I": "Composer", "D-II.A": "Authority", "D-II.B": "Advocate",
        "D-II.C": "Provocateur", "D-III": "Frame-Setter", "D-IV": "Face-Claimer",
        "D-V": "Differentiator", "E-I": "Dualist", "E-II": "Overclaimer",
        "E-III": "Categorizer", "E-IV": "Traditionalist", "E-V": "Epistemic Imperialist",
    },
    "Wren": {
        "D-I": "Side-Participant", "D-II.A": "Seeker", "D-II.B": "Analyst",
        "D-II.C": "Stoic", "D-III": "Frame-Rider", "D-IV": "Face-Guardian",
        "D-V": "Aligner", "E-I": "Evaluativist", "E-II": "Underclaimer",
        "E-III": "Logician", "E-IV": "Institutionalist", "E-V": "Epistemic Pragmatist",
    },
    "Noor": {
        "D-I": "Addressee", "D-II.A": "Authority", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Frame-Breaker", "D-IV": "Face-Guardian",
        "D-V": "Code-Switcher/Bridge", "E-I": "Evaluativist", "E-II": "Knower (K+)",
        "E-III": "Categorizer", "E-IV": "Experientialist", "E-V": "Epistemic Justice Advocate",
    },
    "Ash": {
        "D-I": "Mouthpiece", "D-II.A": "Authority", "D-II.B": "Critic",
        "D-II.C": "Provocateur", "D-III": "Frame-Breaker", "D-IV": "Face-Claimer",
        "D-V": "Differentiator", "E-I": "Multiplist", "E-II": "Overclaimer",
        "E-III": "Consensus-Invoker", "E-IV": "Autodidact", "E-V": "Epistemic Relativist",
    },
    "Linden": {
        "D-I": "Addressee", "D-II.A": "Hedger", "D-II.B": "Analyst",
        "D-II.C": "Empathizer", "D-III": "Reframer", "D-IV": "Face-Negotiator",
        "D-V": "Code-Switcher/Bridge", "E-I": "Meta-Epistemologist", "E-II": "Calibrator",
        "E-III": "Stake Manager", "E-IV": "Pluralist", "E-V": "Epistemic Egalitarian",
    },
    "Rio": {
        "D-I": "Addressee", "D-II.A": "Seeker", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Frame-Rider", "D-IV": "Face-Guardian",
        "D-V": "Aligner", "E-I": "Dualist", "E-II": "Unknower (K-)",
        "E-III": "Consensus-Invoker", "E-IV": "Institutionalist", "E-V": "Epistemic Egalitarian",
    },
    "Vesper": {
        "D-I": "Composer", "D-II.A": "Skeptic", "D-II.B": "Critic",
        "D-II.C": "Stoic", "D-III": "Footing-Shifter", "D-IV": "Face-Ignorer",
        "D-V": "Performer", "E-I": "Evaluativist", "E-II": "Calibrator",
        "E-III": "Logician", "E-IV": "Institutionalist", "E-V": "Epistemic Gatekeeper",
    },
    "Ember": {
        "D-I": "Mouthpiece", "D-II.A": "Authority", "D-II.B": "Advocate",
        "D-II.C": "Provocateur", "D-III": "Frame-Setter", "D-IV": "Face-Threatener",
        "D-V": "Narrator", "E-I": "Multiplist", "E-II": "Overclaimer",
        "E-III": "Narrativist", "E-IV": "Crowd-Sourcer", "E-V": "Epistemic Imperialist",
    },
    "Idris": {
        "D-I": "Composer", "D-II.A": "Authority", "D-II.B": "Analyst",
        "D-II.C": "Empathizer", "D-III": "Frame-Setter", "D-IV": "Face-Guardian",
        "D-V": "Narrator", "E-I": "Meta-Epistemologist", "E-II": "Knower (K+)",
        "E-III": "Narrativist", "E-IV": "Experientialist", "E-V": "Epistemic Egalitarian",
    },
    "Quinn": {
        "D-I": "Addressee", "D-II.A": "Skeptic", "D-II.B": "Critic",
        "D-II.C": "Stoic", "D-III": "Frame-Breaker", "D-IV": "Face-Threatener",
        "D-V": "Gatekeeper", "E-I": "Evaluativist", "E-II": "Epistemic Challenger",
        "E-III": "Logician", "E-IV": "Institutionalist", "E-V": "Epistemic Gatekeeper",
    },
    "Dove": {
        "D-I": "Side-Participant", "D-II.A": "Hedger", "D-II.B": "Advocate",
        "D-II.C": "Empathizer", "D-III": "Frame-Rider", "D-IV": "Face-Guardian",
        "D-V": "Aligner", "E-I": "Evaluativist", "E-II": "Underclaimer",
        "E-III": "Consensus-Invoker", "E-IV": "Crowd-Sourcer", "E-V": "Epistemic Egalitarian",
    },
    "Zara": {
        "D-I": "Overhearer", "D-II.A": "Skeptic", "D-II.B": "Analyst",
        "D-II.C": "Stoic", "D-III": "Footing-Shifter", "D-IV": "Face-Ignorer",
        "D-V": "Differentiator", "E-I": "Meta-Epistemologist", "E-II": "Calibrator",
        "E-III": "Deconstructionist", "E-IV": "Autodidact", "E-V": "Epistemic Relativist",
    },
}

DIMENSIONS = [
    "D-I", "D-II.A", "D-II.B", "D-II.C", "D-III", "D-IV",
    "D-V", "E-I", "E-II", "E-III", "E-IV", "E-V",
]


def _build_dimension_vocab() -> dict[str, dict[str, int]]:
    vocab: dict[str, dict[str, int]] = {}
    for dim in DIMENSIONS:
        values: set[str] = set()
        for agent_dims in ASSIGNMENT_MATRIX.values():
            values.add(agent_dims[dim])
        vocab[dim] = {v: i for i, v in enumerate(sorted(values))}
    return vocab


def _agent_to_onehot(agent_dims: dict[str, str], vocab: dict[str, dict[str, int]]) -> np.ndarray:
    parts = []
    for dim in DIMENSIONS:
        n_values = len(vocab[dim])
        vec = np.zeros(n_values)
        idx = vocab[dim].get(agent_dims[dim])
        if idx is not None:
            vec[idx] = 1.0
        parts.append(vec)
    return np.concatenate(parts)


@dataclass
class ProfileRecoveryResult:
    agent_comparisons: list[dict[str, Any]] = field(default_factory=list)
    archetype_factor_correlation: float = 0.0
    archetype_factor_p_value: float = 1.0
    archetype_factor_spearman: float = 0.0
    archetype_factor_spearman_p: float = 1.0
    n_agents_matched: int = 0
    n_agents_total: int = 0


def compute_profile_recovery(rater_factors: list[dict[str, Any]]) -> ProfileRecoveryResult:
    matched_agents: list[tuple[str, dict[str, str], np.ndarray]] = []
    for rf in rater_factors:
        name = rf.get("agent_name")
        if not name or name not in ASSIGNMENT_MATRIX:
            continue
        vec = np.array([rf.get("intercept", 0.0), rf.get("factor1", 0.0)])
        matched_agents.append((name, ASSIGNMENT_MATRIX[name], vec))

    if len(matched_agents) < 3:
        return ProfileRecoveryResult(n_agents_matched=len(matched_agents), n_agents_total=len(rater_factors))

    vocab = _build_dimension_vocab()
    n = len(matched_agents)

    archetype_vectors = [_agent_to_onehot(dims, vocab) for _, dims, _ in matched_agents]
    factor_vectors = [fv for _, _, fv in matched_agents]

    archetype_dists: list[float] = []
    factor_dists: list[float] = []

    for i in range(n):
        for j in range(i + 1, n):
            a_norm_i = np.linalg.norm(archetype_vectors[i])
            a_norm_j = np.linalg.norm(archetype_vectors[j])
            if a_norm_i > 0 and a_norm_j > 0:
                a_sim = 1.0 - cosine(archetype_vectors[i], archetype_vectors[j])
            else:
                a_sim = 0.0
            archetype_dists.append(a_sim)

            f_norm_i = np.linalg.norm(factor_vectors[i])
            f_norm_j = np.linalg.norm(factor_vectors[j])
            if f_norm_i > 0 and f_norm_j > 0:
                f_sim = 1.0 - cosine(factor_vectors[i], factor_vectors[j])
            else:
                f_sim = 0.0
            factor_dists.append(f_sim)

    pearson_result = pearsonr(archetype_dists, factor_dists)  # type: ignore[arg-type]
    spearman_result = spearmanr(archetype_dists, factor_dists)  # type: ignore[arg-type]

    agent_comparisons = []
    for name, dims, fv in matched_agents:
        closest_by_archetype = None
        closest_by_factors = None
        best_arch_sim = -1.0
        best_fac_sim = -1.0

        for other_name, other_dims, other_fv in matched_agents:
            if other_name == name:
                continue
            a_vec = _agent_to_onehot(dims, vocab)
            o_vec = _agent_to_onehot(other_dims, vocab)
            a_norm = np.linalg.norm(a_vec)
            o_norm = np.linalg.norm(o_vec)
            if a_norm > 0 and o_norm > 0:
                a_sim = 1.0 - cosine(a_vec, o_vec)
            else:
                a_sim = 0.0
            if a_sim > best_arch_sim:
                best_arch_sim = a_sim
                closest_by_archetype = other_name

            f_norm = np.linalg.norm(fv)
            of_norm = np.linalg.norm(other_fv)
            if f_norm > 0 and of_norm > 0:
                f_sim = 1.0 - cosine(fv, other_fv)
            else:
                f_sim = 0.0
            if f_sim > best_fac_sim:
                best_fac_sim = f_sim
                closest_by_factors = other_name

        agent_comparisons.append({
            "name": name,
            "dimensions": {k: dims[k] for k in ["D-I", "D-II.A", "E-II", "E-V"]},
            "intercept": float(fv[0]),
            "factor1": float(fv[1]),
            "closest_by_archetype": closest_by_archetype,
            "closest_by_factors": closest_by_factors,
            "match": closest_by_archetype == closest_by_factors,
        })

    return ProfileRecoveryResult(
        agent_comparisons=agent_comparisons,
        archetype_factor_correlation=float(pearson_result[0]),
        archetype_factor_p_value=float(pearson_result[1]),
        archetype_factor_spearman=float(spearman_result[0]),
        archetype_factor_spearman_p=float(spearman_result[1]),
        n_agents_matched=n,
        n_agents_total=len(rater_factors),
    )
