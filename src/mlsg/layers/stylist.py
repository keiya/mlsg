"""Stylist Layer - generates writer persona and style guidelines."""

from __future__ import annotations

from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import StoryState, Stylist
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "07_stylist.md"


def generate_stylist(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
) -> Result[StoryState, StoryError]:
    """Generate writer persona and style guidelines.

    Args:
        state: Current story state with mpbv and characters
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader

    Returns:
        Updated state with stylist set
    """
    logger.info("layer_started", layer="stylist")

    # Check prerequisite
    if state.mpbv is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="mpbv is required for stylist generation",
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
    layer_config = config.get_layer_config("stylist")
    model = config.get_model_for_layer("stylist")

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
            logger.error("layer_failed", layer="stylist", error=error.message)
            return Failure(error)
        case Success(response_text):
            pass

    # Create the Stylist
    stylist = Stylist(raw_markdown=response_text)

    # Update state
    new_state = replace(state, stylist=stylist)

    logger.info(
        "layer_completed",
        layer="stylist",
        output_length=len(response_text),
    )

    return Success(new_state)


__all__ = ["generate_stylist"]
