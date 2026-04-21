from enum import Enum


class LLMConfigCreateProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    VERTEX_AI = "vertex_ai"

    def __str__(self) -> str:
        return str(self.value)
