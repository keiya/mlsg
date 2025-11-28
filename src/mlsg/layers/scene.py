"""Scene Layer - generates scene narrative text."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import Scene, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "08_scene.md"


def _parse_scene_markdown(raw: str) -> Result[tuple[str, str], StoryError]:
    """Parse Scene output into (text, next_scene_intent).

    Expected format:
    # 本文
    (narrative text)

    # 次のシーンで描くこと
    (next scene intent)
    """
    # Try to find the sections
    text_pattern = r"#\s*本文\s*\n([\s\S]*?)(?=#\s*次のシーンで描くこと|$)"
    intent_pattern = r"#\s*次のシーンで描くこと\s*\n([\s\S]*?)$"

    text_match = re.search(text_pattern, raw, re.IGNORECASE)
    intent_match = re.search(intent_pattern, raw, re.IGNORECASE)

    if text_match:
        text = text_match.group(1).strip()
    else:
        # If no "# 本文" section found, use the whole response
        # but try to remove the intent section
        text = re.sub(r"#\s*次のシーンで描くこと[\s\S]*$", "", raw, flags=re.IGNORECASE).strip()

    intent = intent_match.group(1).strip() if intent_match else ""

    if not text:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message="Could not extract scene text from response",
            )
        )

    return Success((text, intent))


def generate_scene(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
    chapter_index: int,
    scene_index: int,
) -> Result[StoryState, StoryError]:
    """Generate a single scene's narrative text.

    Args:
        state: Current story state
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader
        chapter_index: Index of the chapter
        scene_index: Index of the scene within the chapter (0-based)

    Returns:
        Updated state with new scene added
    """
    logger.info(
        "layer_started",
        layer="scene",
        chapter_index=chapter_index,
        scene_index=scene_index,
    )

    # Check prerequisites
    if state.mpbv is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="mpbv is required for scene generation",
            )
        )

    chapter = state.get_chapter_by_index(chapter_index)
    if chapter is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message=f"chapter {chapter_index} is required for scene generation",
            )
        )

    # Get timeline for this chapter
    timeline = state.get_timeline_by_chapter(chapter_index)
    timeline_str = json.dumps(timeline.to_dict(), ensure_ascii=False) if timeline else "{}"

    # Get all scenes up to this point (including previous chapters)
    all_previous_scenes = [
        s for s in state.scenes
        if s.chapter_index < chapter_index
        or (s.chapter_index == chapter_index and s.scene_index < scene_index)
    ]

    # Build story so far text
    # Include all previous scenes, grouped by chapter
    previous_scenes_text = ""
    if all_previous_scenes:
        scenes_by_chapter: dict[int, list[Scene]] = {}
        for s in all_previous_scenes:
            if s.chapter_index not in scenes_by_chapter:
                scenes_by_chapter[s.chapter_index] = []
            scenes_by_chapter[s.chapter_index].append(s)

        parts: list[str] = []
        for ch_idx in sorted(scenes_by_chapter.keys()):
            ch = state.get_chapter_by_index(ch_idx)
            ch_title = ch.title if ch else f"第{ch_idx + 1}章"
            parts.append(f"## 第{ch_idx + 1}章: {ch_title}")
            for s in scenes_by_chapter[ch_idx]:
                parts.append(s.text)
        previous_scenes_text = "\n\n".join(parts)

    # Determine scene setup from chapter beats
    if scene_index < len(chapter.chapter_beats):
        scene_intent_and_events = chapter.chapter_beats[scene_index]
        scene_title = f"シーン {scene_index + 1}"
    else:
        scene_intent_and_events = chapter.chapter_beats[-1] if chapter.chapter_beats else ""
        scene_title = f"シーン {scene_index + 1}"

    # Get next beat to prevent LLM from jumping ahead
    if scene_index + 1 < len(chapter.chapter_beats):
        next_scene_beat = chapter.chapter_beats[scene_index + 1]
    else:
        next_scene_beat = ""

    # Get stylist guidance if available
    stylist_guidance = state.stylist.raw_markdown if state.stylist else ""

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        mpbv=state.mpbv.to_combined_markdown(),
        charactors=state.get_characters_markdown(),
        timeline=timeline_str,
        stylist=stylist_guidance,
        n=chapter_index + 1,
        scene_title=scene_title,
        m=scene_index + 1,
        story_so_far_full_text=previous_scenes_text or "(まだシーンがありません)",
        scene_intent_and_events=scene_intent_and_events,
        next_scene_beat=next_scene_beat,
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("scene")
    model = config.get_model_for_layer("scene")

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
                layer="scene",
                chapter_index=chapter_index,
                scene_index=scene_index,
                error=error.message,
            )
            return Failure(error)
        case Success(response_text):
            pass

    # Parse the scene
    parse_result = _parse_scene_markdown(response_text)

    match parse_result:
        case Failure(error):
            logger.error(
                "layer_failed",
                layer="scene",
                chapter_index=chapter_index,
                scene_index=scene_index,
                error=error.message,
            )
            return Failure(error)
        case Success((text, next_intent)):
            pass

    # Determine if this is the final scene for the chapter
    is_final_scene = scene_index >= len(chapter.chapter_beats) - 1

    # Create the Scene
    scene = Scene(
        chapter_index=chapter_index,
        scene_index=scene_index,
        scene_title=scene_title,
        text=text,
        next_scene_intent=next_intent,
        is_final_scene=is_final_scene,
    )

    # Update state - add the new scene
    new_scenes = list(state.scenes)
    # Replace if exists, otherwise append
    existing_idx = next(
        (
            i
            for i, s in enumerate(new_scenes)
            if s.chapter_index == chapter_index and s.scene_index == scene_index
        ),
        None,
    )
    if existing_idx is not None:
        new_scenes[existing_idx] = scene
    else:
        new_scenes.append(scene)

    new_state = replace(state, scenes=new_scenes)

    logger.info(
        "layer_completed",
        layer="scene",
        chapter_index=chapter_index,
        scene_index=scene_index,
        is_final=is_final_scene,
        text_length=len(text),
    )

    return Success(new_state)


__all__ = ["generate_scene"]
