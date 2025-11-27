"""Retry logic for LLM calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from returns.result import Failure, Result, Success

from ..config import RetryConfig
from ..errors import ErrorKind, StoryError
from ..logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryHandler:
    """Handles retry logic with exponential backoff."""

    config: RetryConfig

    def is_retryable(self, error: StoryError) -> bool:
        """Check if an error should trigger a retry."""
        retryable_kinds = {
            ErrorKind.LLM_RATE_LIMITED,
            ErrorKind.LLM_CALL_FAILED,  # Network errors, server errors
        }
        return error.kind in retryable_kinds

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed)."""
        delay = self.config.initial_delay * (self.config.exponential_base**attempt)
        return min(delay, self.config.max_delay)

    def execute(
        self,
        operation: Callable[[], Result[T, StoryError]],
        *,
        operation_name: str = "operation",
    ) -> Result[T, StoryError]:
        """Execute an operation with retry logic.

        Args:
            operation: A callable that returns a Result
            operation_name: Name for logging purposes

        Returns:
            The result of the operation, or the last error if all retries fail
        """
        last_error: StoryError | None = None

        for attempt in range(self.config.max_retries + 1):
            result = operation()

            match result:
                case Success(_):
                    if attempt > 0:
                        logger.info(
                            "retry_succeeded",
                            operation=operation_name,
                            attempt=attempt,
                        )
                    return result

                case Failure(error):
                    last_error = error

                    if not self.is_retryable(error):
                        logger.warning(
                            "non_retryable_error",
                            operation=operation_name,
                            error_kind=error.kind.name,
                            message=error.message,
                        )
                        return result

                    if attempt < self.config.max_retries:
                        delay = self.calculate_delay(attempt)
                        logger.warning(
                            "retrying",
                            operation=operation_name,
                            attempt=attempt + 1,
                            max_retries=self.config.max_retries,
                            delay_seconds=delay,
                            error_kind=error.kind.name,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "max_retries_exceeded",
                            operation=operation_name,
                            max_retries=self.config.max_retries,
                            error_kind=error.kind.name,
                            message=error.message,
                        )

        # Should not reach here, but handle just in case
        if last_error:
            return Failure(last_error)
        return Failure(
            StoryError(
                kind=ErrorKind.INVALID_STATE,
                message="Retry loop exited without result",
            )
        )


__all__ = ["RetryHandler"]
