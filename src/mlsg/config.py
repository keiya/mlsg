"""Configuration management for mlsg2."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from returns.result import Failure, Result, Success

from .errors import ErrorKind, StoryError


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


@dataclass(frozen=True)
class LimitsConfig:
    """Configuration for generation limits."""

    max_chapters: int = 20
    max_scenes_per_chapter: int = 10
    max_retries: int = 3
    max_parse_retries: int = 2


@dataclass(frozen=True)
class ModelsConfig:
    """Configuration for model selection."""

    default: str = "claude-sonnet-4-20250514"
    validation: str = "claude-sonnet-4-20250514"
    naming: str = "claude-3-5-haiku-20241022"


@dataclass(frozen=True)
class LayerConfig:
    """Configuration for a single layer."""

    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 8192
    thinking: bool = False
    thinking_budget: int | None = None


@dataclass(frozen=True)
class Config:
    """Root configuration object."""

    language: str = "ja"
    runs_dir: str = "runs"
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    layers: dict[str, LayerConfig] = field(default_factory=dict)

    def get_layer_config(self, layer_name: str) -> LayerConfig:
        """Get configuration for a specific layer, with defaults."""
        return self.layers.get(layer_name, LayerConfig())

    def get_model_for_layer(self, layer_name: str) -> str:
        """Get the model to use for a specific layer."""
        layer_config = self.get_layer_config(layer_name)
        if layer_config.model:
            return layer_config.model
        return self.models.default


def _parse_layer_config(data: dict[str, object]) -> LayerConfig:
    """Parse a layer configuration from TOML data."""
    model = data.get("model")
    temperature_raw = data.get("temperature")
    max_tokens_raw = data.get("max_tokens")
    thinking_budget_raw = data.get("thinking_budget")

    # Parse with type-safe defaults
    temperature = (
        float(temperature_raw) if isinstance(temperature_raw, (int, float)) else 0.7
    )
    max_tokens = int(max_tokens_raw) if isinstance(max_tokens_raw, (int, float)) else 8192
    thinking_budget = (
        int(thinking_budget_raw) if isinstance(thinking_budget_raw, (int, float)) else None
    )

    return LayerConfig(
        model=str(model) if model is not None else None,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking=bool(data.get("thinking", False)),
        thinking_budget=thinking_budget,
    )


def load_config(path: Path | None = None) -> Result[Config, StoryError]:
    """Load configuration from a TOML file.

    If no path is provided, looks for config.toml in the current directory
    and then in the package directory.
    """
    if path is None:
        # Try current directory first
        path = Path("config.toml")
        if not path.exists():
            # Try package directory
            path = Path(__file__).parent.parent.parent / "config.toml"

    if not path.exists():
        # Return default config if no file found
        return Success(Config())

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.CONFIG_ERROR,
                message=f"Invalid TOML in config file: {e}",
            )
        )
    except OSError as e:
        return Failure(
            StoryError(
                kind=ErrorKind.IO_ERROR,
                message=f"Failed to read config file: {e}",
            )
        )

    # Parse general section
    general = data.get("general", {})
    language = str(general.get("language", "ja"))
    runs_dir = str(general.get("runs_dir", "runs"))

    # Parse limits
    limits_data = data.get("limits", {})
    limits = LimitsConfig(
        max_chapters=int(limits_data.get("max_chapters", 20)),
        max_scenes_per_chapter=int(limits_data.get("max_scenes_per_chapter", 10)),
        max_retries=int(limits_data.get("max_retries", 3)),
        max_parse_retries=int(limits_data.get("max_parse_retries", 2)),
    )

    # Parse models
    models_data = data.get("models", {})
    models = ModelsConfig(
        default=str(models_data.get("default", "claude-sonnet-4-20250514")),
        validation=str(models_data.get("validation", "claude-sonnet-4-20250514")),
        naming=str(models_data.get("naming", "claude-3-5-haiku-20241022")),
    )

    # Parse retry
    retry_data = data.get("retry", {})
    retry = RetryConfig(
        max_retries=int(retry_data.get("max_retries", 3)),
        initial_delay=float(retry_data.get("initial_delay", 1.0)),
        max_delay=float(retry_data.get("max_delay", 60.0)),
        exponential_base=float(retry_data.get("exponential_base", 2.0)),
    )

    # Parse layers
    layers_data = data.get("layers", {})
    layers: dict[str, LayerConfig] = {}
    for layer_name, layer_data in layers_data.items():
        if isinstance(layer_data, dict):
            layers[layer_name] = _parse_layer_config(layer_data)

    return Success(
        Config(
            language=language,
            runs_dir=runs_dir,
            limits=limits,
            models=models,
            retry=retry,
            layers=layers,
        )
    )


__all__ = [
    "Config",
    "LayerConfig",
    "LimitsConfig",
    "ModelsConfig",
    "RetryConfig",
    "load_config",
]
