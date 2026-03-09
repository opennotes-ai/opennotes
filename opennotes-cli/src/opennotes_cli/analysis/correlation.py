from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import cosine, squareform


@dataclass
class RaterVector:
    name: str
    intercept: float
    factor1: float

    @property
    def vector(self) -> np.ndarray:
        return np.array([self.intercept, self.factor1])


@dataclass
class ClusterInfo:
    cluster_id: int
    members: list[str]
    mean_similarity: float


@dataclass
class CorrelationResult:
    similarity_matrix: np.ndarray
    labels: list[str]
    clusters: list[ClusterInfo]
    most_similar_pairs: list[tuple[str, str, float]]
    most_different_pairs: list[tuple[str, str, float]]


def compute_correlation_matrix(rater_factors: list[dict[str, Any]]) -> CorrelationResult:
    raters = [
        RaterVector(
            name=rf.get("agent_name") or rf.get("rater_id", "unknown"),
            intercept=rf.get("intercept", 0.0),
            factor1=rf.get("factor1", 0.0),
        )
        for rf in rater_factors
    ]

    n = len(raters)
    labels = [r.name for r in raters]

    sim_matrix = np.ones((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            vi = raters[i].vector
            vj = raters[j].vector
            norm_i = np.linalg.norm(vi)
            norm_j = np.linalg.norm(vj)
            if norm_i == 0 or norm_j == 0:
                sim = 0.0
            else:
                sim = 1.0 - cosine(vi, vj)
            sim_matrix[i, j] = sim
            sim_matrix[j, i] = sim

    dist_matrix = 1.0 - sim_matrix
    np.fill_diagonal(dist_matrix, 0.0)
    dist_matrix = np.clip(dist_matrix, 0.0, None)

    condensed = squareform(dist_matrix)
    Z = linkage(condensed, method="ward")

    max_d = np.median(Z[:, 2]) * 1.2
    cluster_labels = fcluster(Z, t=max_d, criterion="distance")

    clusters: dict[int, list[int]] = {}
    for idx, cid in enumerate(cluster_labels):
        clusters.setdefault(int(cid), []).append(idx)

    cluster_infos = []
    for cid, members_idx in sorted(clusters.items()):
        member_names = [labels[i] for i in members_idx]
        sims = []
        for i in range(len(members_idx)):
            for j in range(i + 1, len(members_idx)):
                sims.append(sim_matrix[members_idx[i], members_idx[j]])
        mean_sim = float(np.mean(sims)) if sims else 1.0
        cluster_infos.append(ClusterInfo(cid, member_names, mean_sim))

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((labels[i], labels[j], float(sim_matrix[i, j])))

    pairs.sort(key=lambda x: x[2], reverse=True)
    most_similar = pairs[:5]
    most_different = pairs[-5:][::-1]

    return CorrelationResult(
        similarity_matrix=sim_matrix,
        labels=labels,
        clusters=cluster_infos,
        most_similar_pairs=most_similar,
        most_different_pairs=most_different,
    )
