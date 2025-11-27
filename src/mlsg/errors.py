from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ErrorKind(Enum):
    """High-level classification for errors in the story generation pipeline."""

    # LLM-related errors
    LLM_CALL_FAILED = auto()
    LLM_RATE_LIMITED = auto()
    LLM_CONTEXT_TOO_LONG = auto()

    # Parse errors
    PARSE_ERROR = auto()
    JSON_INVALID = auto()
    MARKDOWN_MALFORMED = auto()

    # State errors
    INVALID_STATE = auto()
    MISSING_PREREQUISITE = auto()

    # I/O and config errors
    IO_ERROR = auto()
    CONFIG_ERROR = auto()


@dataclass(frozen=True)
class StoryError:
    """Structured error used with Result[T, StoryError].

    This is the unified error type for the story generation pipeline.
    The `kind` field provides high-level classification, while `message`
    gives a human-readable description. The optional `detail` field can
    hold structured diagnostic data.

    Example:
        StoryError(
            kind=ErrorKind.LLM_RATE_LIMITED,
            message="Rate limit exceeded, retry after 60 seconds",
            detail={"retry_after": 60, "model": "claude-sonnet-4-5-20250514"}
        )
    """

    kind: ErrorKind
    message: str
    detail: dict[str, object] | None = None


__all__ = ["ErrorKind", "StoryError"]
