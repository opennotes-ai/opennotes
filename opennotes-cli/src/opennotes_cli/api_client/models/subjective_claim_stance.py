from enum import Enum


class SubjectiveClaimStance(str, Enum):
    EVALUATES = "evaluates"
    OPPOSES = "opposes"
    SUPPORTS = "supports"

    def __str__(self) -> str:
        return str(self.value)
