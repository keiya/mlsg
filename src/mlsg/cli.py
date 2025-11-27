"""CLI for mlsg2 - Multi-Layered Story Generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from returns.result import Failure, Success

from . import __version__
from .config import load_config
from .domain import StoryState
from .errors import ErrorKind, StoryError
from .llm.prompts import PromptLoader
from .logging import console, print_error, print_info, print_success, setup_logging
from .persistence import load_state, save_state
from .pipeline import LayerName, create_client, generate_run_name, run_pipeline
from .result import Result


def _read_seed(args: argparse.Namespace) -> Result[str, StoryError]:
    """Read seed input from args or stdin."""
    if hasattr(args, "seed") and args.seed:
        return Success(args.seed)

    if hasattr(args, "file") and args.file:
        seed_path = Path(args.file)
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
        except OSError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.IO_ERROR,
                    message=f"Failed to read seed file: {e}",
                )
            )

    # Read from stdin if available
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return Success(data.strip())

    return Failure(
        StoryError(
            kind=ErrorKind.INVALID_STATE,
            message="No seed input provided. Use positional argument, -f, or pipe to stdin.",
        )
    )


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the story generation pipeline."""
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    # Load configuration
    config_result = load_config()
    match config_result:
        case Failure(error):
            print_error(f"Failed to load config: {error.message}")
            return 1
        case Success(config):
            pass

    # Create client
    client = create_client(config)

    # Create prompt loader
    prompt_loader = PromptLoader()

    # Initialize or load state
    if args.from_dir:
        # Load existing state
        from_path = Path(args.from_dir)
        if from_path.is_dir():
            # Find the latest state file
            state_files = sorted(from_path.glob("state_*.json"))
            if not state_files:
                print_error(f"No state files found in {from_path}")
                return 1
            state_path = state_files[-1]
        else:
            state_path = from_path

        state_result = load_state(state_path)
        match state_result:
            case Failure(error):
                print_error(f"Failed to load state: {error.message}")
                return 1
            case Success(state):
                print_info(f"Loaded state from {state_path}")

        runs_dir = from_path if from_path.is_dir() else from_path.parent
    else:
        # Create new state from seed
        seed_result = _read_seed(args)
        match seed_result:
            case Failure(error):
                print_error(error.message)
                return 1
            case Success(seed):
                pass

        # Generate or use provided run name
        if args.name:
            run_name = args.name
        else:
            name_result = generate_run_name(seed, client, config)
            match name_result:
                case Failure(_):
                    run_name = "story"
                case Success(name):
                    run_name = name

        print_info(f"Run name: {run_name}")

        state = StoryState(seed_input=seed, run_name=run_name)

        # Create runs directory
        runs_dir = Path(config.runs_dir) / run_name
        runs_dir.mkdir(parents=True, exist_ok=True)

        # Save initial state
        save_state(state, runs_dir / "state_00_init.json")

    # Parse layer options
    until: LayerName | None = args.until if hasattr(args, "until") else None
    only: LayerName | None = args.only if hasattr(args, "only") else None

    # Progress callback
    def on_progress(layer: str, current: int, total: int) -> None:
        if not args.quiet:
            console.print(f"[cyan][{current}/{total}][/cyan] {layer}...", end=" ")

    # Run pipeline
    result = run_pipeline(
        state,
        client,
        config,
        prompt_loader,
        until=until,
        only=only,
        runs_dir=runs_dir,
        on_progress=on_progress if not args.quiet else None,
    )

    match result:
        case Failure(error):
            print_error(f"\nPipeline failed: {error.message}")
            return 1
        case Success(final_state):
            pass

    if not args.quiet:
        console.print()  # Newline after progress

    print_success(
        f"Story generated: {len(final_state.chapters)} chapters, {len(final_state.scenes)} scenes"
    )
    print_info(f"Output: {runs_dir}")

    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show status of a run."""
    setup_logging(quiet=True)

    # Find the run directory
    if args.run_dir:
        run_path = Path(args.run_dir)
    else:
        # Find the most recent run
        config_result = load_config()
        match config_result:
            case Failure(error):
                print_error(f"Failed to load config: {error.message}")
                return 1
            case Success(config):
                pass

        runs_dir = Path(config.runs_dir)
        if not runs_dir.exists():
            print_error("No runs directory found")
            return 1

        run_dirs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        if not run_dirs:
            print_error("No runs found")
            return 1

        run_path = run_dirs[-1]

    if not run_path.exists():
        print_error(f"Run not found: {run_path}")
        return 1

    # Find state files
    state_files = sorted(run_path.glob("state_*.json"))
    if not state_files:
        print_error(f"No state files in {run_path}")
        return 1

    # Load the latest state
    latest_state_path = state_files[-1]
    state_result = load_state(latest_state_path)
    match state_result:
        case Failure(error):
            print_error(f"Failed to load state: {error.message}")
            return 1
        case Success(state):
            pass

    # Display status
    console.print(f"[bold]Run:[/bold] {run_path.name}")
    console.print(f"[bold]State files:[/bold] {len(state_files)}")
    console.print(f"[bold]Latest:[/bold] {latest_state_path.name}")
    console.print()

    console.print("[bold]Progress:[/bold]")
    console.print(f"  Master Plot: {'✓' if state.master_plot else '✗'}")
    console.print(f"  Backstories: {'✓' if state.backstories else '✗'}")
    console.print(f"  MPBV: {'✓' if state.mpbv else '✗'}")
    console.print(f"  Characters: {len(state.characters)} defined")
    console.print(f"  Stylist: {'✓' if state.stylist else '✗'}")
    console.print(f"  Chapters: {len(state.chapters)}")
    console.print(f"  Timelines: {len(state.timelines)}")
    console.print(f"  Scenes: {len(state.scenes)}")

    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Export the story to markdown."""
    setup_logging(quiet=True)

    # Find the run directory
    if args.run_dir:
        run_path = Path(args.run_dir)
    else:
        config_result = load_config()
        match config_result:
            case Failure(error):
                print_error(f"Failed to load config: {error.message}")
                return 1
            case Success(config):
                pass

        runs_dir = Path(config.runs_dir)
        run_dirs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        if not run_dirs:
            print_error("No runs found")
            return 1
        run_path = run_dirs[-1]

    # Find the latest state
    state_files = sorted(run_path.glob("state_*.json"))
    if not state_files:
        print_error(f"No state files in {run_path}")
        return 1

    state_result = load_state(state_files[-1])
    match state_result:
        case Failure(error):
            print_error(f"Failed to load state: {error.message}")
            return 1
        case Success(state):
            pass

    # Build markdown output
    lines: list[str] = []
    lines.append(f"# {state.run_name or 'Story'}")
    lines.append("")

    for chapter in state.chapters:
        lines.append(f"## 第{chapter.index + 1}章: {chapter.title}")
        lines.append("")

        chapter_scenes = state.get_scenes_for_chapter(chapter.index)
        for scene in chapter_scenes:
            lines.append(scene.text)
            lines.append("")

    output = "\n".join(lines)

    # Write to file or stdout
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8")
        print_success(f"Exported to {output_path}")
    else:
        console.print(output)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mlsg",
        description="Multi-Layered Story Generator",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run story generation pipeline")
    run_parser.add_argument("seed", nargs="?", help="Story seed text")
    run_parser.add_argument("-f", "--file", help="Read seed from file")
    run_parser.add_argument("--from", dest="from_dir", help="Resume from existing run")
    run_parser.add_argument("--name", help="Name for this run")
    run_parser.add_argument(
        "--until",
        choices=["plot", "backstory", "mpbv", "character", "stylist", "chapter", "timeline", "scene"],
        help="Stop after this layer",
    )
    run_parser.add_argument(
        "--only",
        choices=["plot", "backstory", "mpbv", "character", "stylist", "chapter", "timeline", "scene"],
        help="Run only this layer",
    )
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    run_parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    run_parser.set_defaults(func=_cmd_run)

    # status command
    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("run_dir", nargs="?", help="Run directory")
    status_parser.set_defaults(func=_cmd_status)

    # export command
    export_parser = subparsers.add_parser("export", help="Export story to markdown")
    export_parser.add_argument("run_dir", nargs="?", help="Run directory")
    export_parser.add_argument("-o", "--output", help="Output file path")
    export_parser.set_defaults(func=_cmd_export)

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
