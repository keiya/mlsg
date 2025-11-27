"""Pipeline orchestration for story generation."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Literal

from returns.result import Failure, Result, Success

from .config import Config
from .domain import StoryState
from .errors import ErrorKind, StoryError
from .layers import (
    generate_backstories,
    generate_chapter,
    generate_characters,
    generate_master_plot,
    generate_scene,
    generate_stylist,
    generate_timeline,
    validate_mpbv,
)
from .llm.client import AnthropicClient, LLMClient
from .llm.prompts import PromptLoader
from .logging import get_logger
from .persistence import save_state

logger = get_logger(__name__)

LayerName = Literal[
    "plot", "backstory", "mpbv", "character", "stylist", "chapter", "timeline", "scene"
]

LAYER_ORDER: list[LayerName] = [
    "plot",
    "backstory",
    "mpbv",
    "character",
    "stylist",
    "chapter",
    "timeline",
    "scene",
]


def _sanitize_run_name(name: str) -> str:
    """Sanitize a run name for use as a directory name.

    Allows: alphanumeric, Japanese characters (hiragana, katakana, kanji),
    underscores, and hyphens.
    """
    # Remove or replace invalid characters
    # Keep: \w (word chars), Japanese hiragana, katakana, kanji
    sanitized = re.sub(r"[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\-]", "_", name)
    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")
    # Limit length
    return sanitized[:50] or "story"


def generate_run_name(
    seed_input: str,
    client: LLMClient,
    config: Config,
) -> Result[str, StoryError]:
    """Generate a short, descriptive name for the run using Haiku."""
    prompt = f"""以下のストーリーのシードから、短い日本語のタイトル（5〜15文字程度）を1つだけ生成してください。
記号や括弧は使わないでください。タイトルのみを出力してください。

シード:
{seed_input[:500]}

タイトル:"""

    result = client.complete(
        prompt,
        model=config.models.naming,
        temperature=0.7,
        max_tokens=50,
    )

    match result:
        case Failure(error):
            # Fallback to a generic name
            logger.warning("run_name_generation_failed", error=error.message)
            return Success("story")
        case Success(name):
            sanitized = _sanitize_run_name(name.strip())
            return Success(sanitized)
        case _ as unreachable:  # pragma: no cover
            # This should never happen, but satisfies exhaustiveness check
            raise AssertionError(f"Unreachable: {unreachable}")


def run_pipeline(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
    *,
    until: LayerName | None = None,
    only: LayerName | None = None,
    runs_dir: Path | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> Result[StoryState, StoryError]:
    """Run the story generation pipeline.

    Args:
        state: Initial story state
        client: LLM client
        config: Configuration
        prompt_loader: Prompt template loader
        until: Stop after this layer (inclusive)
        only: Run only this layer
        runs_dir: Directory to save intermediate states
        on_progress: Callback for progress updates (layer_name, current, total)

    Returns:
        Final story state
    """
    logger.info("pipeline_started", until=until, only=only)

    # Determine which layers to run
    if only:
        layers_to_run = [only]
    elif until:
        until_idx = LAYER_ORDER.index(until)
        layers_to_run = LAYER_ORDER[: until_idx + 1]
    else:
        layers_to_run = list(LAYER_ORDER)

    total_steps = len(layers_to_run)
    current_step = 0

    # Helper to save state
    def save_checkpoint(state: StoryState, suffix: str) -> None:
        if runs_dir:
            state_path = runs_dir / f"state_{suffix}.json"
            save_state(state, state_path)

    # Run each layer
    for layer in layers_to_run:
        current_step += 1
        if on_progress:
            on_progress(layer, current_step, total_steps)

        logger.info("running_layer", layer=layer, step=f"{current_step}/{total_steps}")

        match layer:
            case "plot":
                result = generate_master_plot(state, client, config, prompt_loader)
                match result:
                    case Failure(error):
                        return Failure(error)
                    case Success(new_state):
                        state = new_state
                        save_checkpoint(state, "01_plot")

            case "backstory":
                result = generate_backstories(state, client, config, prompt_loader)
                match result:
                    case Failure(error):
                        return Failure(error)
                    case Success(new_state):
                        state = new_state
                        save_checkpoint(state, "02_backstory")

            case "mpbv":
                result = validate_mpbv(state, client, config, prompt_loader)
                match result:
                    case Failure(error):
                        return Failure(error)
                    case Success(new_state):
                        state = new_state
                        save_checkpoint(state, "03_mpbv")

            case "character":
                result = generate_characters(state, client, config, prompt_loader)
                match result:
                    case Failure(error):
                        return Failure(error)
                    case Success(new_state):
                        state = new_state
                        save_checkpoint(state, "04_character")

            case "stylist":
                result = generate_stylist(state, client, config, prompt_loader)
                match result:
                    case Failure(error):
                        return Failure(error)
                    case Success(new_state):
                        state = new_state
                        save_checkpoint(state, "05_stylist")

            case "chapter":
                # Generate chapters iteratively
                chapter_index = len(state.chapters)
                max_chapters = config.limits.max_chapters

                while chapter_index < max_chapters:
                    result = generate_chapter(
                        state, client, config, prompt_loader, chapter_index
                    )
                    match result:
                        case Failure(error):
                            return Failure(error)
                        case Success(new_state):
                            state = new_state
                            save_checkpoint(state, f"06_chapter_{chapter_index + 1:02d}")

                    # Check if this is the final chapter
                    chapter = state.get_chapter_by_index(chapter_index)
                    if chapter and chapter.is_final_chapter:
                        break

                    chapter_index += 1

            case "timeline":
                # Generate timeline for each chapter
                for chapter in state.chapters:
                    result = generate_timeline(
                        state, client, config, prompt_loader, chapter.index
                    )
                    match result:
                        case Failure(error):
                            return Failure(error)
                        case Success(new_state):
                            state = new_state
                            save_checkpoint(
                                state, f"07_timeline_{chapter.index + 1:02d}"
                            )

            case "scene":
                # Generate scenes for each chapter
                max_scenes = config.limits.max_scenes_per_chapter

                for chapter in state.chapters:
                    scene_index = len(state.get_scenes_for_chapter(chapter.index))

                    # Generate scenes up to the number of beats or max
                    target_scenes = min(len(chapter.chapter_beats), max_scenes)

                    while scene_index < target_scenes:
                        result = generate_scene(
                            state,
                            client,
                            config,
                            prompt_loader,
                            chapter.index,
                            scene_index,
                        )
                        match result:
                            case Failure(error):
                                return Failure(error)
                            case Success(new_state):
                                state = new_state
                                save_checkpoint(
                                    state,
                                    f"08_scene_{chapter.index + 1:02d}_{scene_index + 1:02d}",
                                )

                        # Check if this is the final scene
                        scene = new_state.scenes[-1] if new_state.scenes else None
                        if scene and scene.is_final_scene:
                            break

                        scene_index += 1

    # Save final state
    if runs_dir:
        save_checkpoint(state, "final")

    logger.info("pipeline_completed", num_chapters=len(state.chapters), num_scenes=len(state.scenes))
    return Success(state)


def create_client(config: Config) -> AnthropicClient:
    """Create an LLM client from configuration."""
    return AnthropicClient(
        default_model=config.models.default,
        retry_config=config.retry,
    )


__all__ = [
    "LayerName",
    "create_client",
    "generate_run_name",
    "run_pipeline",
]
