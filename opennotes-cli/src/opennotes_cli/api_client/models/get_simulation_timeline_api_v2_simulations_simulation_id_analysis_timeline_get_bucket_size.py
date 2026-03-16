from enum import Enum


class GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize(
    str, Enum
):
    AUTO = "auto"
    HOUR = "hour"
    MINUTE = "minute"

    def __str__(self) -> str:
        return str(self.value)
