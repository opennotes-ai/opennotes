from enum import Enum


class ActionTier(str, Enum):
    TIER_1_IMMEDIATE = "tier_1_immediate"
    TIER_2_CONSENSUS = "tier_2_consensus"

    def __str__(self) -> str:
        return str(self.value)
