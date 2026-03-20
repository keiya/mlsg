"""Backstory Layer - generates world settings from the master plot."""

from __future__ import annotations

from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import Backstories, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "02_backstory.md"


def generate_backstories(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
) -> Result[StoryState, StoryError]:
    """Generate world settings (backstories) from the master plot.

    Args:
        state: Current story state with master_plot
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader

    Returns:
        Updated state with backstories set
    """
    logger.info("layer_started", layer="backstory")

    # Check prerequisite
    if state.master_plot is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="master_plot is required for backstory generation",
            )
        )

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        seed_input=state.seed_input,
        master_plot=state.master_plot.raw_markdown,
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("backstory")
    model = config.get_model_for_layer("backstory")

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
            logger.error("layer_failed", layer="backstory", error=error.message)
            return Failure(error)
        case Success(response_text):
            pass

    # Create the Backstories
    backstories = Backstories(raw_markdown=response_text)

    # Update state
    new_state = replace(state, backstories=backstories)

    logger.info(
        "layer_completed",
        layer="backstory",
        output_length=len(response_text),
    )

    return Success(new_state)


__all__ = ["generate_backstories"]
