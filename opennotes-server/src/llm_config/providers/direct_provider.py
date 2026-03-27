from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.direct import model_request, model_request_stream
from pydantic_ai.messages import (
    ModelRequest as PydanticModelRequest,
)
from pydantic_ai.messages import (
    ModelResponse as PydanticModelResponse,
)
from pydantic_ai.messages import (
    PartDeltaEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.settings import ModelSettings

from src.llm_config.model_id import ModelId
from src.llm_config.providers.base import LLMMessage, LLMProvider, LLMResponse, ProviderSettings
from src.monitoring import get_logger

logger = get_logger(__name__)


class EmptyLLMResponseError(Exception):
    pass


class DirectProviderSettings(ProviderSettings):
    model_config = ConfigDict(extra="forbid")

    timeout: float = Field(30.0, gt=0)
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class DirectCompletionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelId | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None


class DirectProvider(LLMProvider[DirectProviderSettings, DirectCompletionParams]):
    def __init__(
        self,
        api_key: str | None,
        default_model: str,
        settings: DirectProviderSettings,
        provider_name: str = "openai",
    ) -> None:
        super().__init__(api_key, default_model, settings)
        self._provider_name = provider_name

    def _build_model_settings(self, params: DirectCompletionParams) -> ModelSettings:
        settings: dict[str, Any] = {
            "max_tokens": params.max_tokens or self.settings.max_tokens,
            "temperature": params.temperature
            if params.temperature is not None
            else self.settings.temperature,
            "timeout": self.settings.timeout,
        }
        if params.top_p is not None:
            settings["top_p"] = params.top_p
        if params.frequency_penalty is not None:
            settings["frequency_penalty"] = params.frequency_penalty
        if params.presence_penalty is not None:
            settings["presence_penalty"] = params.presence_penalty
        return ModelSettings(**settings)  # type: ignore[misc]

    async def complete(
        self, messages: list[LLMMessage], params: DirectCompletionParams | None = None
    ) -> LLMResponse:
        params = params or DirectCompletionParams()
        model_str = params.model.to_pydantic_ai() if params.model else self.default_model

        if not model_str:
            raise ValueError(
                "Model name cannot be empty. Check that RELEVANCE_CHECK_MODEL, "
                "DEFAULT_FULL_MODEL, or other model configuration is set correctly."
            )

        pydantic_messages = self._convert_messages(messages)
        model_settings = self._build_model_settings(params)

        logger.debug(
            "Direct provider completion request",
            extra={
                "model": model_str,
                "max_tokens": model_settings.get("max_tokens"),
                "message_count": len(messages),
            },
        )

        response = await model_request(
            model=model_str,
            messages=pydantic_messages,
            model_settings=model_settings,
        )

        content = response.text or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        finish_reason = response.finish_reason or "stop"

        logger.info(
            "LLM completion finished",
            extra={
                "model": model_str,
                "finish_reason": finish_reason,
                "content_length": len(content),
                "tokens_used": tokens_used,
            },
        )

        if not content:
            logger.warning(
                "LLM returned empty content",
                extra={"finish_reason": finish_reason, "model": model_str},
            )

        return LLMResponse(
            content=content,
            model=response.model_name or model_str,
            tokens_used=tokens_used,
            finish_reason=finish_reason,
            provider=self._provider_name,
        )

    async def stream_complete(
        self, messages: list[LLMMessage], params: DirectCompletionParams | None = None
    ) -> AsyncGenerator[str, None]:
        params = params or DirectCompletionParams()
        model_str = params.model.to_pydantic_ai() if params.model else self.default_model

        if not model_str:
            raise ValueError(
                "Model name cannot be empty. Check that model configuration is set correctly."
            )

        pydantic_messages = self._convert_messages(messages)
        model_settings = self._build_model_settings(params)

        async with model_request_stream(
            model=model_str,
            messages=pydantic_messages,
            model_settings=model_settings,
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    yield event.delta.content_delta

    def _convert_messages(
        self, messages: list[LLMMessage]
    ) -> list[PydanticModelRequest | PydanticModelResponse]:
        result: list[PydanticModelRequest | PydanticModelResponse] = []
        for msg in messages:
            if msg.role == "system":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                result.append(PydanticModelRequest.user_text_prompt("", instructions=content))
            elif msg.role == "user":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                result.append(PydanticModelRequest.user_text_prompt(content))
            elif msg.role == "assistant":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                result.append(PydanticModelResponse(parts=[TextPart(content=content)]))
        return result

    async def validate_api_key(self) -> bool:
        if self._provider_name in ("vertex_ai", "gemini"):
            return True
        try:
            await model_request(
                model=self.default_model,
                messages=[PydanticModelRequest.user_text_prompt("test")],
                model_settings=ModelSettings(max_tokens=1),  # type: ignore[misc]
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await super().close()
