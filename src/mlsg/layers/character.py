"""Character Layer - generates character sheets from MPBV."""

from __future__ import annotations

import re
from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import Character, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "04_charactor.md"


def _parse_characters(response_text: str) -> list[Character]:
    """Parse characters from the response text.

    Looks for sections starting with ## [Name] (role: ...)
    """
    characters: list[Character] = []

    # Split by character sections (## followed by character name)
    # Pattern matches: ## キャラクター名 (役割: ...) or ## [キャラクター名]
    pattern = r"^##\s+(.+?)(?:\s*\(役割[:：]\s*(.+?)\)|\s*\[(.+?)\])?\s*$"

    # Split the text into sections by "## " at the start of lines
    sections = re.split(r"\n(?=##\s+[^\#])", response_text)

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split("\n")
        if not lines:
            continue

        first_line = lines[0]
        match = re.match(pattern, first_line)

        if match:
            name = match.group(1).strip()
            # Remove any markdown formatting from name
            name = re.sub(r"[\[\]]", "", name).strip()

            role = match.group(2) or match.group(3) or "unknown"
            role = role.strip()

            # The rest is the raw markdown for this character
            raw_markdown = section.strip()

            characters.append(
                Character(
                    name=name,
                    role=role,
                    raw_markdown=raw_markdown,
                )
            )

    return characters


def generate_characters(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
) -> Result[StoryState, StoryError]:
    """Generate character sheets from MPBV.

    Args:
        state: Current story state with mpbv
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader

    Returns:
        Updated state with characters set
    """
    logger.info("layer_started", layer="character")

    # Check prerequisite
    if state.mpbv is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="mpbv is required for character generation",
            )
        )

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        mpbv=state.mpbv.to_combined_markdown(),
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("character")
    model = config.get_model_for_layer("character")

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
            logger.error("layer_failed", layer="character", error=error.message)
            return Failure(error)
        case Success(response_text):
            pass

    # Parse characters from response
    characters = _parse_characters(response_text)

    if not characters:
        # If parsing failed, create a single character with the full response
        characters = [
            Character(
                name="Characters",
                role="all",
                raw_markdown=response_text,
            )
        ]
        logger.warning(
            "character_parse_fallback",
            message="Could not parse individual characters, using full response",
        )

    # Update state
    new_state = replace(state, characters=characters)

    logger.info(
        "layer_completed",
        layer="character",
        num_characters=len(characters),
        output_length=len(response_text),
    )

    return Success(new_state)


__all__ = ["generate_characters"]
