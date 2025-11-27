from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .domain import StoryState
from .errors import ErrorKind, StoryError
from .result import Failure, Result, Success


def _load_seed(args: argparse.Namespace) -> Result[str, StoryError]:
    """Load the seed input from a file or stdin."""
    if args.seed_file:
        seed_path = Path(args.seed_file)
        try:
            seed = seed_path.read_text(encoding="utf-8")
            return Success(seed.strip())
        except FileNotFoundError:
            return Failure(
                StoryError(
                    kind=ErrorKind.IO_ERROR,
                    message=f"Seed file not found: {seed_path}",
                )
            )
        except PermissionError:
            return Failure(
                StoryError(
                    kind=ErrorKind.IO_ERROR,
                    message=f"Permission denied reading: {seed_path}",
                )
            )
        except OSError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.IO_ERROR,
                    message=f"Failed to read seed file: {e}",
                )
            )
    else:
        data = sys.stdin.read()
        if not data.strip():
            return Failure(
                StoryError(
                    kind=ErrorKind.INVALID_STATE,
                    message="No seed input provided (stdin was empty)",
                )
            )
        return Success(data.strip())


def _cmd_init(args: argparse.Namespace) -> int:
    """Initialize a StoryState from a seed input and print a short summary.

    This is a prototype; no LLM calls are made yet.
    """
    result = _load_seed(args)

    match result:
        case Success(seed):
            state = StoryState(seed_input=seed)
            sys.stdout.write("Initialized StoryState\n")
            sys.stdout.write(f"- seed length: {len(state.seed_input)} chars\n")
            return 0
        case Failure(error):
            sys.stderr.write(f"Error [{error.kind.name}]: {error.message}\n")
            return 1
        case _:
            # This case should never be reached due to Result being
            # exhaustively Success | Failure
            sys.stderr.write("Internal error: unexpected result type\n")
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mlsg",
        description="Multi Layered Story Generator (experimental CLI)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a story state from a seed input",
    )
    init_parser.add_argument(
        "-s",
        "--seed-file",
        type=str,
        help="Path to a file containing the story seed (defaults to stdin)",
    )
    init_parser.set_defaults(func=_cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
