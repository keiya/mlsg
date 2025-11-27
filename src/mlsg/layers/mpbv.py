"""MPBV Layer - validates and unifies master plot + backstories."""

from __future__ import annotations

import re
from dataclasses import replace

from returns.result import Failure, Result, Success

from ..config import Config
from ..domain import MPBV, StoryState
from ..errors import ErrorKind, StoryError
from ..llm.client import LLMClient
from ..llm.prompts import PromptLoader
from ..logging import get_logger

logger = get_logger(__name__)

TEMPLATE_NAME = "03_master_plot_and_backstory_validation.md"


def _parse_mpbv_response(response_text: str) -> Result[MPBV, StoryError]:
    """Parse the MPBV response into separate master plot and backstories sections."""
    # Look for the "# Master Plot" and "# Backstories" sections
    master_plot_pattern = r"#\s*Master\s*Plot\s*\n(.*?)(?=#\s*Backstories|$)"
    backstories_pattern = r"#\s*Backstories\s*\n(.*?)$"

    master_plot_match = re.search(master_plot_pattern, response_text, re.DOTALL | re.IGNORECASE)
    backstories_match = re.search(backstories_pattern, response_text, re.DOTALL | re.IGNORECASE)

    if not master_plot_match:
        # Try to find any content before "# Backstories" as master plot
        if "# Backstories" in response_text or "#Backstories" in response_text:
            parts = re.split(r"#\s*Backstories", response_text, maxsplit=1, flags=re.IGNORECASE)
            master_plot_markdown = parts[0].strip()
            backstories_markdown = parts[1].strip() if len(parts) > 1 else ""
        else:
            return Failure(
                StoryError(
                    kind=ErrorKind.PARSE_ERROR,
                    message="Could not find Master Plot section in MPBV response",
                )
            )
    else:
        master_plot_markdown = master_plot_match.group(1).strip()
        backstories_markdown = backstories_match.group(1).strip() if backstories_match else ""

    # Add section headers back
    master_plot_markdown = f"# Master Plot\n\n{master_plot_markdown}"
    backstories_markdown = f"# Backstories\n\n{backstories_markdown}"

    return Success(
        MPBV(
            master_plot_markdown=master_plot_markdown,
            backstories_markdown=backstories_markdown,
        )
    )


def validate_mpbv(
    state: StoryState,
    client: LLMClient,
    config: Config,
    prompt_loader: PromptLoader,
) -> Result[StoryState, StoryError]:
    """Validate and unify master plot + backstories.

    This layer takes the raw master plot and backstories, checks for
    logical contradictions, and produces a unified, validated version.

    Args:
        state: Current story state with master_plot and backstories
        client: LLM client for generation
        config: Configuration
        prompt_loader: Prompt template loader

    Returns:
        Updated state with mpbv set
    """
    logger.info("layer_started", layer="mpbv")

    # Check prerequisites
    if state.master_plot is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="master_plot is required for MPBV validation",
            )
        )
    if state.backstories is None:
        return Failure(
            StoryError(
                kind=ErrorKind.MISSING_PREREQUISITE,
                message="backstories is required for MPBV validation",
            )
        )

    # Combine master plot and backstories as input
    combined_input = f"""# 原案: マスタープロット

{state.master_plot.raw_markdown}

# 原案: 世界観設定 (Backstories)

{state.backstories.raw_markdown}
"""

    # Render the prompt template
    prompt_result = prompt_loader.render(
        TEMPLATE_NAME,
        user_input=combined_input,
    )

    match prompt_result:
        case Failure(error):
            return Failure(error)
        case Success(prompt):
            pass

    # Get layer config
    layer_config = config.get_layer_config("mpbv")
    model = config.get_model_for_layer("mpbv")

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
            logger.error("layer_failed", layer="mpbv", error=error.message)
            return Failure(error)
        case Success(response_text):
            pass

    # Parse the response into MPBV
    mpbv_result = _parse_mpbv_response(response_text)

    match mpbv_result:
        case Failure(error):
            logger.error("layer_failed", layer="mpbv", error=error.message)
            return Failure(error)
        case Success(mpbv):
            pass

    # Update state
    new_state = replace(state, mpbv=mpbv)

    logger.info(
        "layer_completed",
        layer="mpbv",
        output_length=len(response_text),
    )

    return Success(new_state)


__all__ = ["validate_mpbv"]
