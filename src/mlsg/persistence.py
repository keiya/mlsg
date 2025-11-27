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
                context_summary=s["context_summary"],
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


__all__ = [
    "from_json",
    "load_state",
    "save_state",
    "to_json",
]
