"""Prompt template loading and rendering."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from returns.result import Failure, Result, Success

from ..errors import ErrorKind, StoryError
from ..logging import get_logger

logger = get_logger(__name__)


class PromptLoader:
    """Loads and renders prompt templates using Jinja2."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt templates.
                        If None, uses the prompts/ directory relative to the project root.
        """
        if prompts_dir is None:
            # Default to prompts/ in the project root
            prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"

        self.prompts_dir = prompts_dir
        self.env = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            autoescape=False,  # We're generating prompts, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(
        self,
        template_name: str,
        **variables: object,
    ) -> Result[str, StoryError]:
        """Render a prompt template with the given variables.

        Args:
            template_name: Name of the template file (e.g., "01_master_plot.md")
            **variables: Variables to pass to the template

        Returns:
            The rendered prompt text
        """
        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**variables)

            logger.debug(
                "prompt_rendered",
                template=template_name,
                variables=list(variables.keys()),
                length=len(rendered),
            )

            return Success(rendered)

        except TemplateNotFound:
            return Failure(
                StoryError(
                    kind=ErrorKind.CONFIG_ERROR,
                    message=f"Prompt template not found: {template_name}",
                    detail={"prompts_dir": str(self.prompts_dir)},
                )
            )
        except Exception as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.PARSE_ERROR,
                    message=f"Failed to render template {template_name}: {e}",
                )
            )

    def load_raw(self, template_name: str) -> Result[str, StoryError]:
        """Load a template file without rendering.

        Useful for inspecting templates or when no variables are needed.
        """
        template_path = self.prompts_dir / template_name

        try:
            content = template_path.read_text(encoding="utf-8")
            return Success(content)
        except FileNotFoundError:
            return Failure(
                StoryError(
                    kind=ErrorKind.CONFIG_ERROR,
                    message=f"Prompt file not found: {template_name}",
                )
            )
        except OSError as e:
            return Failure(
                StoryError(
                    kind=ErrorKind.IO_ERROR,
                    message=f"Failed to read prompt file: {e}",
                )
            )


__all__ = ["PromptLoader"]
