from enum import Enum


class LLMConfigTestRequestProvider(str, Enum):
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    CUSTOM = "custom"
    GOOGLE = "google"
    OPENAI = "openai"

    def __str__(self) -> str:
        return str(self.value)
