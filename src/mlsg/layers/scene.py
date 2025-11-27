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

    # Get scenes for this chapter
    chapter_scenes = state.get_scenes_for_chapter(chapter_index)

    # Get previous scene summary and intent
    previous_scene_summary = ""
    if chapter_scenes:
        # Get the last scene's summary
        last_scene = chapter_scenes[-1]
        previous_scene_summary = last_scene.context_summary or f"直前のシーン: {last_scene.scene_title}"

    # Get previous scenes text (up to last 3)
    previous_scenes_text = ""
    recent_scenes = chapter_scenes[-3:] if len(chapter_scenes) > 0 else []
    if recent_scenes:
        previous_scenes_text = "\n\n---\n\n".join(
            f"### {s.scene_title}\n\n{s.text}" for s in recent_scenes
        )

    # Determine scene setup from chapter beats
    if scene_index < len(chapter.chapter_beats):
        scene_intent_and_events = chapter.chapter_beats[scene_index]
        scene_title = f"シーン {scene_index + 1}"
    else:
        scene_intent_and_events = chapter.chapter_beats[-1] if chapter.chapter_beats else ""
        scene_title = f"シーン {scene_index + 1}"

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        mpbv=state.mpbv.to_combined_markdown(),
        charactors=state.get_characters_markdown(),
        timeline=timeline_str,
        n=chapter_index + 1,
        scene_title=scene_title,
        m=scene_index + 1,
        previous_scene_summary=previous_scene_summary or "(最初のシーンです)",
        story_so_far_full_text=previous_scenes_text or "(まだシーンがありません)",
        scene_intent_and_events=scene_intent_and_events,
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
        context_summary=f"シーン {scene_index + 1}: {scene_intent_and_events[:100]}...",
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
