"""Chapter Layer - generates chapter structure from MPBV and characters."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import Chapter, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "05_chapter.md"


def _parse_chapter_json(raw: str, chapter_index: int) -> Result[Chapter, StoryError]:
    """Parse the JSON output from Chapter Layer prompt."""
    # Try to extract JSON from markdown code block if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try to find raw JSON
        json_str = raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.JSON_INVALID,
                message=f"Failed to parse chapter JSON: {e}",
                detail={"raw": raw[:500]},
            )
        )

    try:
        chapter = Chapter(
            index=chapter_index,
            title=data.get("chapter_title", f"Chapter {chapter_index + 1}"),
            theme=data.get("chapter_theme", ""),
            chapter_beats=data.get("chapter_beats", []),
            active_characters=data.get("active_characters", []),
            is_final_chapter=data.get("is_final_chapter", False),
            next_chapter_intent=data.get("next_chapter_intent", ""),
        )
        return Success(chapter)
    except (KeyError, TypeError) as e:
        return Failure(
            StoryError(
                kind=ErrorKind.PARSE_ERROR,
                message=f"Invalid chapter data structure: {e}",
            )
        )


def generate_chapter(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
    chapter_index: int,
) -> Result[StoryState, StoryError]:
    """Generate a single chapter's structure.

    Args:
        state: Current story state with mpbv and characters
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader
        chapter_index: Index of the chapter to generate (0-based)

    Returns:
        Updated state with new chapter added
    """
    logger.info("layer_started", layer="chapter", chapter_index=chapter_index)

    # Check prerequisites
    if state.mpbv is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="mpbv is required for chapter generation",
            )
        )

    # Get previous chapter info if available
    previous_chapter_summary = ""
    previous_chapter_intent = ""

    if chapter_index > 0 and state.chapters:
        prev_chapter = state.get_chapter_by_index(chapter_index - 1)
        if prev_chapter:
            previous_chapter_summary = f"第{chapter_index}章「{prev_chapter.title}」\nテーマ: {prev_chapter.theme}\nビート:\n" + "\n".join(
                f"- {beat}" for beat in prev_chapter.chapter_beats
            )
            previous_chapter_intent = prev_chapter.next_chapter_intent

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        n=chapter_index + 1,  # 1-indexed for display
        max_chapters=config.limits.max_chapters,
        mpbv=state.mpbv.to_combined_markdown(),
        previous_chapter_summary=previous_chapter_summary or "(最初の章です)",
        previous_chapter_intent=previous_chapter_intent or "(なし)",
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("chapter")
    model = config.get_model_for_layer("chapter")

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
                "layer_failed", layer="chapter", chapter_index=chapter_index, error=error.message
            )
            return Failure(error)
        case Success(response_text):
            pass

    # Parse the chapter JSON
    chapter_result = _parse_chapter_json(response_text, chapter_index)

    match chapter_result:
        case Failure(error):
            logger.error(
                "layer_failed",
                layer="chapter",
                chapter_index=chapter_index,
                error=error.message,
            )
            return Failure(error)
        case Success(chapter):
            pass

    # Update state - add the new chapter
    new_chapters = list(state.chapters)
    # Replace if exists, otherwise append
    existing_idx = next(
        (i for i, c in enumerate(new_chapters) if c.index == chapter_index), None
    )
    if existing_idx is not None:
        new_chapters[existing_idx] = chapter
    else:
        new_chapters.append(chapter)

    new_state = replace(state, chapters=new_chapters)

    logger.info(
        "layer_completed",
        layer="chapter",
        chapter_index=chapter_index,
        chapter_title=chapter.title,
        is_final=chapter.is_final_chapter,
        num_beats=len(chapter.chapter_beats),
    )

    return Success(new_state)


__all__ = ["generate_chapter"]
