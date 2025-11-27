"""Timeline Layer - extracts timeline events from chapters."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import StoryState, TimelineSlice
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "06_timeline.md"


def _parse_timeline_json(
    raw: str, chapter_index: int
) -> Result[TimelineSlice, StoryError]:
    """Parse the JSON output from Timeline Layer prompt."""
    # Try to extract JSON from markdown code block if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try to find raw JSON (look for { ... })
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.JSON_INVALID,
                message=f"Failed to parse timeline JSON: {e}",
                detail={"raw": raw[:500]},
            )
        )

    try:
        # Convert the raw JSON format to TimelineSlice
        timeline = TimelineSlice.from_raw_json(chapter_index, data)
        return Success(timeline)
    except (KeyError, TypeError) as e:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message=f"Invalid timeline data structure: {e}",
            )
        )


def generate_timeline(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
    chapter_index: int,
) -> Result[StoryState, StoryError]:
    """Generate timeline for a specific chapter.

    Args:
        state: Current story state
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader
        chapter_index: Index of the chapter to generate timeline for

    Returns:
        Updated state with new timeline added
    """
    logger.info("layer_started", layer="timeline", chapter_index=chapter_index)

    # Check prerequisites
    if state.mpbv is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="mpbv is required for timeline generation",
            )
        )

    chapter = state.get_chapter_by_index(chapter_index)
    if chapter is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message=f"chapter {chapter_index} is required for timeline generation",
            )
        )

    # Get previous timeline info
    last_date = "不明"
    last_event_summary = "物語開始前"

    if chapter_index > 0:
        prev_timeline = state.get_timeline_by_chapter(chapter_index - 1)
        if prev_timeline and prev_timeline.characters:
            # Get the most recent event from any character
            latest_events: list[tuple[str, str, str]] = []
            for char_name, char_timeline in prev_timeline.characters.items():
                if char_timeline.events:
                    last_event = max(char_timeline.events, key=lambda e: e.datetime)
                    latest_events.append(
                        (last_event.datetime, char_name, last_event.description)
                    )
            if latest_events:
                latest = max(latest_events, key=lambda x: x[0])
                last_date = latest[0]
                last_event_summary = f"{latest[1]}: {latest[2]}"

    # Format chapter plot
    current_chapter_plot = f"""第{chapter_index + 1}章「{chapter.title}」
テーマ: {chapter.theme}

ビート:
""" + "\n".join(f"- {beat}" for beat in chapter.chapter_beats)

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        chapter_number=chapter_index + 1,
        mpbv=state.mpbv.to_combined_markdown(),
        charactors=state.get_characters_markdown(),
        last_date=last_date,
        last_event_summary=last_event_summary,
        current_chapter_plot=current_chapter_plot,
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("timeline")
    model = config.get_model_for_layer("timeline")

    # Call the LLM
    response_result = client.complete(
        prompt,
        model=model,
        temperature=layer_config.temperature,
        max_tokens=layer_config.max_tokens,
        thinking=layer_config.thinking,
        thinking_budget=layer_config.thinking_budget,
    )

    match response_result:
        case Failure(error):
            logger.error(
                "layer_failed",
                layer="timeline",
                chapter_index=chapter_index,
                error=error.message,
            )
            return Failure(error)
        case Success(response_text):
            pass

    # Parse the timeline JSON
    timeline_result = _parse_timeline_json(response_text, chapter_index)

    match timeline_result:
        case Failure(error):
            logger.error(
                "layer_failed",
                layer="timeline",
                chapter_index=chapter_index,
                error=error.message,
            )
            return Failure(error)
        case Success(timeline):
            pass

    # Update state - add the new timeline
    new_timelines = list(state.timelines)
    # Replace if exists, otherwise append
    existing_idx = next(
        (i for i, t in enumerate(new_timelines) if t.chapter_index == chapter_index),
        None,
    )
    if existing_idx is not None:
        new_timelines[existing_idx] = timeline
    else:
        new_timelines.append(timeline)

    new_state = replace(state, timelines=new_timelines)

    logger.info(
        "layer_completed",
        layer="timeline",
        chapter_index=chapter_index,
        num_characters=len(timeline.characters),
    )

    return Success(new_state)


__all__ = ["generate_timeline"]
