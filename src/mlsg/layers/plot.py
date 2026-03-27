"""Plot Layer - generates the master plot from a seed input."""

from __future__ import annotations

from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import MasterPlot, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "01_master_plot.md"


def generate_master_plot(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
) -> Result[StoryState, StoryError]:
    """Generate the master plot from the seed input.

    Args:
        state: Current story state with seed_input
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader

    Returns:
        Updated state with master_plot set
    """
    logger.info("layer_started", layer="plot")

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        user_input=state.seed_input,
        max_chapters=config.limits.max_chapters,
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("plot")
    model = config.get_model_for_layer("plot")

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
            logger.error("layer_failed", layer="plot", error=error.message)
            return Failure(error)
        case Success(response_text):
            pass

    # Create the MasterPlot
    master_plot = MasterPlot(raw_markdown=response_text)

    # Update state
    new_state = replace(state, master_plot=master_plot)

    logger.info(
        "layer_completed",
        layer="plot",
        output_length=len(response_text),
    )

    return Success(new_state)


__all__ = ["generate_master_plot"]
