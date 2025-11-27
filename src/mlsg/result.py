"""Result type re-exports from the returns library.

This module provides a thin wrapper around `returns.result` to maintain
a consistent API across the codebase while leveraging the well-tested
`returns` library implementation.

Usage:
    from mlsg.result import Result, Success, Failure, safe

    def divide(a: int, b: int) -> Result[float, str]:
        if b == 0:
            return Failure("division by zero")
        return Success(a / b)

    result = divide(10, 2)
    match result:
        case Success(value):
            print(f"Result: {value}")
        case Failure(error):
            print(f"Error: {error}")
"""

from __future__ import annotations

from typing import NoReturn, Sequence, TypeVar

from returns.result import Failure, Result, Success, safe

T = TypeVar("T")
E = TypeVar("E")


def unreachable(msg: str = "unreachable code") -> NoReturn:
    """Signal that a code path should never be reached.

    Use this in exhaustive match statements or after assertions.
    """
    raise RuntimeError(msg)


def aggregate_results(results: Sequence[Result[T, E]]) -> Result[list[T], E]:
    """Aggregate a sequence of Results into a single Result.

    Returns Success with a list of all values if all results are Success.
    Returns the first Failure encountered otherwise.

    Example:
        results = [Success(1), Success(2), Success(3)]
        aggregate_results(results)  # Success([1, 2, 3])

        results = [Success(1), Failure("err"), Success(3)]
        aggregate_results(results)  # Failure("err")
    """
    values: list[T] = []
    for r in results:
        match r:
            case Success(value):
                values.append(value)
            case Failure():
                return r
    return Success(values)


__all__ = [
    "Result",
    "Success",
    "Failure",
    "safe",
    "unreachable",
    "aggregate_results",
]
