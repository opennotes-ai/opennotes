from enum import Enum


class WebRiskFindingThreatTypesItem(str, Enum):
    MALWARE = "MALWARE"
    POTENTIALLY_HARMFUL_APPLICATION = "POTENTIALLY_HARMFUL_APPLICATION"
    SOCIAL_ENGINEERING = "SOCIAL_ENGINEERING"
    UNWANTED_SOFTWARE = "UNWANTED_SOFTWARE"

    def __str__(self) -> str:
        return str(self.value)
