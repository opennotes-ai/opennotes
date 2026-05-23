from enum import Enum


class SourceKind(str, Enum):
    EXTERNAL = "external"
    UTTERANCE = "utterance"

    def __str__(self) -> str:
        return str(self.value)
