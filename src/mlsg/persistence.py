"""Persistence layer for StoryState serialization."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from returns.result import Failure, Result, Success

from .domain import (
    Backstories,
    Chapter,
    Character,
    CharacterTimeline,
    MasterPlot,
    MPBV,
    Scene,
    StoryState,
    Stylist,
    TimelineEvent,
    TimelineSlice,
)
from .errors import ErrorKind, StoryError
from .logging import get_logger

logger = get_logger(__name__)


def _serialize_story_state(state: StoryState) -> dict[str, Any]:
    """Convert StoryState to a JSON-serializable dict."""
    data: dict[str, Any] = {
        "seed_input": state.seed_input,
        "run_name": state.run_name,
    }

    if state.master_plot:
        data["master_plot"] = {"raw_markdown": state.master_plot.raw_markdown}

    if state.backstories:
        data["backstories"] = {"raw_markdown": state.backstories.raw_markdown}

    if state.mpbv:
        data["mpbv"] = {
            "master_plot_markdown": state.mpbv.master_plot_markdown,
            "backstories_markdown": state.mpbv.backstories_markdown,
        }

    if state.characters:
        data["characters"] = [
            {"name": c.name, "role": c.role, "raw_markdown": c.raw_markdown}
            for c in state.characters
        ]

    if state.stylist:
        data["stylist"] = {"raw_markdown": state.stylist.raw_markdown}

    if state.chapters:
        data["chapters"] = [asdict(c) for c in state.chapters]

    if state.timelines:
        data["timelines"] = [
            {
                "chapter_index": t.chapter_index,
                "characters": {
                    name: [asdict(e) for e in timeline.events]
                    for name, timeline in t.characters.items()
                },
            }
            for t in state.timelines
        ]

    if state.scenes:
        data["scenes"] = [asdict(s) for s in state.scenes]

    return data


def _deserialize_story_state(data: dict[str, Any]) -> StoryState:
    """Convert a dict back to StoryState."""
    state = StoryState(
        seed_input=data["seed_input"],
        run_name=data.get("run_name", ""),
    )

    if "master_plot" in data:
        state.master_plot = MasterPlot(raw_markdown=data["master_plot"]["raw_markdown"])

    if "backstories" in data:
        state.backstories = Backstories(
            raw_markdown=data["backstories"]["raw_markdown"]
        )

    if "mpbv" in data:
        state.mpbv = MPBV(
            master_plot_markdown=data["mpbv"]["master_plot_markdown"],
            backstories_markdown=data["mpbv"]["backstories_markdown"],
        )

    if "characters" in data:
        state.characters = [
            Character(name=c["name"], role=c["role"], raw_markdown=c["raw_markdown"])
            for c in data["characters"]
        ]

    if "stylist" in data:
        state.stylist = Stylist(raw_markdown=data["stylist"]["raw_markdown"])

    if "chapters" in data:
        state.chapters = [
            Chapter(
                index=c["index"],
                title=c["title"],
                theme=c["theme"],
                chapter_beats=c["chapter_beats"],
                active_characters=c["active_characters"],
                is_final_chapter=c["is_final_chapter"],
                next_chapter_intent=c["next_chapter_intent"],
            )
            for c in data["chapters"]
        ]

    if "timelines" in data:
        timelines: list[TimelineSlice] = []
        for t in data["timelines"]:
            characters: dict[str, CharacterTimeline] = {}
            for name, events_data in t["characters"].items():
                events = [
                    TimelineEvent(datetime=e["datetime"], description=e["description"])
                    for e in events_data
                ]
                characters[name] = CharacterTimeline(
                    character_name=name, events=events
                )
            timelines.append(
                TimelineSlice(chapter_index=t["chapter_index"], characters=characters)
            )
        state.timelines = timelines

    if "scenes" in data:
        state.scenes = [
            Scene(
                chapter_index=s["chapter_index"],
                scene_index=s["scene_index"],
                scene_title=s["scene_title"],
                text=s["text"],
                next_scene_intent=s["next_scene_intent"],
                is_final_scene=s["is_final_scene"],
            )
            for s in data["scenes"]
        ]

    return state


def to_json(state: StoryState, *, indent: int = 2) -> str:
    """Serialize StoryState to JSON string."""
    data = _serialize_story_state(state)
    return json.dumps(data, ensure_ascii=False, indent=indent)


def from_json(json_str: str) -> Result[StoryState, StoryError]:
    """Deserialize StoryState from JSON string."""
    try:
        data = json.loads(json_str)
        state = _deserialize_story_state(data)
        return Success(state)
    except json.JSONDecodeError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message=f"Invalid JSON: {e}",
            )
        )
    except KeyError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message=f"Missing required field: {e}",
            )
        )
    except Exception as e:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message=f"Failed to deserialize state: {e}",
            )
        )


def save_state(state: StoryState, path: Path) -> Result[None, StoryError]:
    """Save StoryState to a JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        json_str = to_json(state)
        path.write_text(json_str, encoding="utf-8")
        logger.info("state_saved", path=str(path))
        return Success(None)
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to save state: {e}",
            )
        )


def load_state(path: Path) -> Result[StoryState, StoryError]:
    """Load StoryState from a JSON file."""
    try:
        json_str = path.read_text(encoding="utf-8")
        return from_json(json_str)
    except FileNotFoundError:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"State file not found: {path}",
            )
        )
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to read state file: {e}",
            )
        )


def load_external_mpbv(path: Path) -> Result[MPBV, StoryError]:
    """Load MPBV from an external Markdown file.

    Expected format:
    ```
    # Master Plot
    (master plot content)

    # Backstories
    (backstories content)
    ```

    The file is split at "# Backstories" (case-insensitive).
    If not found, the entire content is treated as master_plot_markdown
    and backstories_markdown is left empty.
    """
    import re

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"MPBV file not found: {path}",
            )
        )
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to read MPBV file: {e}",
            )
        )

    # Try to split at "# Backstories" or "# Backstory"
    pattern = r"(?:^|\n)(#\s*Backstor(?:y|ies)\b)"
    match = re.search(pattern, content, re.IGNORECASE)

    if match:
        master_plot_markdown = content[: match.start()].strip()
        backstories_markdown = content[match.start() :].strip()
    else:
        # No split found - treat entire content as combined
        # Try to find "# Master Plot" to clean up
        master_match = re.search(r"^#\s*Master\s*Plot\b", content, re.IGNORECASE | re.MULTILINE)
        if master_match:
            master_plot_markdown = content.strip()
        else:
            master_plot_markdown = content.strip()
        backstories_markdown = ""

    logger.info("external_mpbv_loaded", path=str(path))
    return Success(
        MPBV(
            master_plot_markdown=master_plot_markdown,
            backstories_markdown=backstories_markdown,
        )
    )


def load_external_stylist(path: Path) -> Result[Stylist, StoryError]:
    """Load Stylist from an external Markdown file.

    The entire file content is used as the raw_markdown.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Stylist file not found: {path}",
            )
        )
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to read Stylist file: {e}",
            )
        )

    logger.info("external_stylist_loaded", path=str(path))
    return Success(Stylist(raw_markdown=content.strip()))


def save_layer_markdown(
    runs_dir: Path,
    filename: str,
    content: str,
    *,
    append: bool = False,
) -> Result[None, StoryError]:
    """Save layer output as Markdown file.

    Args:
        runs_dir: Directory to save to
        filename: Filename (e.g., "01_plot.md")
        content: Markdown content to write
        append: If True, append to file (for tail -f support)

    Returns:
        Success or Failure
    """
    try:
        path = runs_dir / filename
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as f:
            f.write(content)
            if append and not content.endswith("\n"):
                f.write("\n")
        logger.debug("layer_markdown_saved", path=str(path), append=append)
        return Success(None)
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to save markdown: {e}",
            )
        )


def export_plot_markdown(state: StoryState, runs_dir: Path) -> Result[None, StoryError]:
    """Export master plot to 01_plot.md."""
    if state.master_plot is None:
        return Success(None)
    return save_layer_markdown(runs_dir, "01_plot.md", state.master_plot.raw_markdown)


def export_backstory_markdown(state: StoryState, runs_dir: Path) -> Result[None, StoryError]:
    """Export backstories to 02_backstory.md."""
    if state.backstories is None:
        return Success(None)
    return save_layer_markdown(runs_dir, "02_backstory.md", state.backstories.raw_markdown)


def export_mpbv_markdown(state: StoryState, runs_dir: Path) -> Result[None, StoryError]:
    """Export MPBV to 03_mpbv.md."""
    if state.mpbv is None:
        return Success(None)
    content = f"{state.mpbv.master_plot_markdown}\n\n---\n\n{state.mpbv.backstories_markdown}"
    return save_layer_markdown(runs_dir, "03_mpbv.md", content)


def export_stylist_markdown(state: StoryState, runs_dir: Path) -> Result[None, StoryError]:
    """Export stylist to 05_stylist.md."""
    if state.stylist is None:
        return Success(None)
    return save_layer_markdown(runs_dir, "05_stylist.md", state.stylist.raw_markdown)


def append_chapter_markdown(
    state: StoryState, runs_dir: Path, chapter_index: int
) -> Result[None, StoryError]:
    """Append a single chapter to 06_chapters.md."""
    chapter = state.get_chapter_by_index(chapter_index)
    if chapter is None:
        return Success(None)

    lines = [
        f"\n## 第{chapter.index + 1}章: {chapter.title}\n",
        f"**テーマ**: {chapter.theme}\n",
        "",
        "### ビート",
    ]
    for i, beat in enumerate(chapter.chapter_beats, 1):
        lines.append(f"{i}. {beat}")
    lines.append("")
    lines.append(f"**登場人物**: {', '.join(chapter.active_characters)}")
    if chapter.is_final_chapter:
        lines.append("\n*（最終章）*")
    lines.append("\n---\n")

    content = "\n".join(lines)
    return save_layer_markdown(runs_dir, "06_chapters.md", content, append=True)


def append_scene_markdown(
    state: StoryState, runs_dir: Path, chapter_index: int, scene_index: int
) -> Result[None, StoryError]:
    """Append a single scene to 08_scenes.md."""
    scenes = [
        s for s in state.scenes
        if s.chapter_index == chapter_index and s.scene_index == scene_index
    ]
    if not scenes:
        return Success(None)

    scene = scenes[0]
    chapter = state.get_chapter_by_index(chapter_index)
    chapter_title = chapter.title if chapter else f"第{chapter_index + 1}章"

    lines = [
        f"\n## 第{chapter_index + 1}章 - シーン{scene_index + 1}",
        f"*{chapter_title}*\n",
        scene.text,
        "\n---\n",
    ]

    content = "\n".join(lines)
    return save_layer_markdown(runs_dir, "08_scenes.md", content, append=True)


__all__ = [
    "append_chapter_markdown",
    "append_scene_markdown",
    "export_backstory_markdown",
    "export_mpbv_markdown",
    "export_plot_markdown",
    "export_stylist_markdown",
    "from_json",
    "load_external_mpbv",
    "load_external_stylist",
    "load_state",
    "save_layer_markdown",
    "save_state",
    "to_json",
]
