"""LLM client implementation."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import anthropic
from anthropic.types import MessageParam, ThinkingConfigEnabledParam
from dotenv import load_dotenv
from returns.result import Failure, Result, Success

from ..config import LayerConfig, RetryConfig
from ..errors import ErrorKind, StoryError
from ..logging import get_logger
from .retry import RetryHandler

logger = get_logger(__name__)

# Load environment variables
load_dotenv()


class LLMClient(Protocol):
    """Protocol for LLM clients."""

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Result[str, StoryError]:
        """Send a prompt and return the completion text."""
        ...

    def complete_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Iterator[Result[str, StoryError]]:
        """Stream completion chunks."""
        ...


@dataclass
class AnthropicClient:
    """Anthropic API client implementation."""

    default_model: str
    retry_config: RetryConfig
    _client: anthropic.Anthropic | None = None

    def __post_init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not found in environment")
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            raise RuntimeError("Anthropic client not initialized - missing API key")
        return self._client

    def _make_request(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        thinking: bool,
        thinking_budget: int | None,
    ) -> Result[str, StoryError]:
        """Make a single API request."""
        try:
            # Build messages with proper type
            messages: list[MessageParam] = [{"role": "user", "content": prompt}]

            # For extended thinking, we need to use the beta API
            if thinking:
                # Extended thinking requires specific setup
                thinking_config: ThinkingConfigEnabledParam = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget or 10000,
                }
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    thinking=thinking_config,
                    messages=messages,
                )
            else:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                )

            # Extract text from response
            text_parts: list[str] = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)

            if not text_parts:
                return Failure(
                    StoryError(
                        kind=ErrorKind.LLM_CALL_FAILED,
                        message="No text content in response",
                    )
                )

            result_text = "\n".join(text_parts)

            logger.debug(
                "llm_request_completed",
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            return Success(result_text)

        except anthropic.RateLimitError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.LLM_RATE_LIMITED,
                    message=f"Rate limit exceeded: {e}",
                )
            )
        except anthropic.APIStatusError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.LLM_CALL_FAILED,
                    message=f"API error: {e}",
                )
            )
        except anthropic.APIConnectionError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.LLM_CALL_FAILED,
                    message=f"Connection error: {e}",
                )
            )

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Result[str, StoryError]:
        """Send a prompt and return the completion text with retry."""
        actual_model = model or self.default_model
        actual_temperature = temperature if temperature is not None else 0.7
        actual_max_tokens = max_tokens or 8192

        retry_handler = RetryHandler(self.retry_config)

        return retry_handler.execute(
            lambda: self._make_request(
                prompt,
                model=actual_model,
                temperature=actual_temperature,
                max_tokens=actual_max_tokens,
                thinking=thinking,
                thinking_budget=thinking_budget,
            ),
            operation_name=f"llm_complete({actual_model})",
        )

    def complete_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Iterator[Result[str, StoryError]]:
        """Stream completion chunks."""
        actual_model = model or self.default_model
        actual_temperature = temperature if temperature is not None else 0.7
        actual_max_tokens = max_tokens or 8192

        try:
            messages: list[MessageParam] = [{"role": "user", "content": prompt}]

            with self.client.messages.stream(
                model=actual_model,
                max_tokens=actual_max_tokens,
                temperature=actual_temperature,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield Success(text)

        except anthropic.RateLimitError as e:
            yield Failure(
                StoryError(
                    kind=ErrorKind.LLM_RATE_LIMITED,
                    message=f"Rate limit exceeded: {e}",
                )
            )
        except anthropic.APIStatusError as e:
            yield Failure(
                StoryError(
                    kind=ErrorKind.LLM_CALL_FAILED,
                    message=f"API error: {e}",
                )
            )
        except anthropic.APIConnectionError as e:
            yield Failure(
                StoryError(
                    kind=ErrorKind.LLM_CALL_FAILED,
                    message=f"Connection error: {e}",
                )
            )

    def complete_with_config(
        self,
        prompt: str,
        config: LayerConfig,
    ) -> Result[str, StoryError]:
        """Complete using a LayerConfig."""
        return self.complete(
            prompt,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            thinking=config.thinking,
            thinking_budget=config.thinking_budget,
        )


__all__ = ["AnthropicClient", "LLMClient"]
