from enum import Enum


class GetSimulationDetailedAnalysisApiV2SimulationsSimulationIdAnalysisDetailedGetSortBy(
    str, Enum
):
    COUNT = "count"
    HAS_SCORE = "has_score"

    def __str__(self) -> str:
        return str(self.value)
