from enum import Enum


class HarmfulContentMatchSource(str, Enum):
    GCP = "gcp"
    OPENAI = "openai"

    def __str__(self) -> str:
        return str(self.value)
