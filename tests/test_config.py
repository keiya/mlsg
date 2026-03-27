"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest
from returns.result import Failure, Success

from mlsg.config import (
    Config,
    LayerConfig,
    LimitsConfig,
    ModelsConfig,
    RetryConfig,
    load_config,
)


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_default_config(self) -> None:
        config = Config()
        assert config.language == "ja"
        assert config.runs_dir == "runs"

    def test_default_limits(self) -> None:
        limits = LimitsConfig()
        assert limits.max_chapters == 3
        assert limits.max_scenes_per_chapter == 4
        assert limits.max_retries == 3
        assert limits.max_parse_retries == 2

    def test_default_models(self) -> None:
        models = ModelsConfig()
        assert "claude" in models.default.lower() or "sonnet" in models.default.lower()
        assert "haiku" in models.naming.lower()

    def test_default_retry(self) -> None:
        retry = RetryConfig()
        assert retry.max_retries == 3
        assert retry.initial_delay == 1.0
        assert retry.max_delay == 60.0
        assert retry.exponential_base == 2.0

    def test_default_layer_config(self) -> None:
        layer = LayerConfig()
        assert layer.model is None
        assert layer.temperature == 0.7
        assert layer.max_tokens == 8192
        assert layer.thinking is False
        assert layer.thinking_budget is None


class TestConfigMethods:
    """Tests for Config methods."""

    def test_get_layer_config_exists(self) -> None:
        config = Config(
            layers={
                "plot": LayerConfig(temperature=1.0, max_tokens=4096),
            }
        )
        layer = config.get_layer_config("plot")
        assert layer.temperature == 1.0
        assert layer.max_tokens == 4096

    def test_get_layer_config_missing(self) -> None:
        config = Config()
        layer = config.get_layer_config("nonexistent")
        # Should return default LayerConfig
        assert layer.temperature == 0.7
        assert layer.max_tokens == 8192

    def test_get_model_for_layer_with_override(self) -> None:
        config = Config(
            models=ModelsConfig(default="default-model"),
            layers={
                "plot": LayerConfig(model="custom-model"),
            },
        )
        assert config.get_model_for_layer("plot") == "custom-model"

    def test_get_model_for_layer_uses_default(self) -> None:
        config = Config(
            models=ModelsConfig(default="default-model"),
            layers={
                "plot": LayerConfig(model=None),  # no override
            },
        )
        assert config.get_model_for_layer("plot") == "default-model"

    def test_get_model_for_layer_missing_layer(self) -> None:
        config = Config(
            models=ModelsConfig(default="default-model"),
        )
        assert config.get_model_for_layer("nonexistent") == "default-model"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_nonexistent_explicit_returns_failure(self) -> None:
        """When an explicit config path doesn't exist, return Failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_config(Path(tmpdir) / "nonexistent.toml")
            assert isinstance(result, Failure)
            assert "not found" in result.failure().message

    def test_load_valid_toml(self) -> None:
        toml_content = """
[general]
language = "en"
runs_dir = "custom_runs"

[limits]
max_chapters = 10
max_scenes_per_chapter = 5

[models]
default = "test-model"
naming = "test-haiku"

[retry]
max_retries = 5
initial_delay = 2.0

[layers.plot]
temperature = 1.0
max_tokens = 16384
thinking = false

[layers.mpbv]
model = "gpt-4"
temperature = 0.5
thinking = true
thinking_budget = 50000
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text(toml_content)

            result = load_config(path)
            assert isinstance(result, Success)
            config = result.unwrap()

            assert config.language == "en"
            assert config.runs_dir == "custom_runs"
            assert config.limits.max_chapters == 10
            assert config.limits.max_scenes_per_chapter == 5
            assert config.models.default == "test-model"
            assert config.retry.max_retries == 5
            assert config.retry.initial_delay == 2.0

            plot_config = config.get_layer_config("plot")
            assert plot_config.temperature == 1.0
            assert plot_config.max_tokens == 16384
            assert plot_config.thinking is False

            mpbv_config = config.get_layer_config("mpbv")
            assert mpbv_config.model == "gpt-4"
            assert mpbv_config.thinking is True
            assert mpbv_config.thinking_budget == 50000

    def test_load_invalid_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text("this is not valid toml [[[")

            result = load_config(path)
            assert isinstance(result, Failure)
            assert "Invalid TOML" in result.failure().message

    def test_load_partial_config(self) -> None:
        """Config with only some sections should use defaults for the rest."""
        toml_content = """
[general]
language = "en"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text(toml_content)

            result = load_config(path)
            assert isinstance(result, Success)
            config = result.unwrap()

            assert config.language == "en"
            # Defaults should be used
            assert config.limits.max_chapters == 20
            assert config.retry.max_retries == 3


class TestLayerConfigParsing:
    """Tests for layer configuration parsing edge cases."""

    def test_layer_with_integer_temperature(self) -> None:
        """Temperature should accept integer and convert to float."""
        toml_content = """
[layers.plot]
temperature = 1
max_tokens = 8192
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text(toml_content)

            result = load_config(path)
            assert isinstance(result, Success)
            config = result.unwrap()

            layer = config.get_layer_config("plot")
            assert layer.temperature == 1.0
            assert isinstance(layer.temperature, float)

    def test_layer_with_all_fields(self) -> None:
        toml_content = """
[layers.chapter]
model = "claude-sonnet"
temperature = 0.7
max_tokens = 32000
thinking = true
thinking_budget = 25000
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            path.write_text(toml_content)

            result = load_config(path)
            assert isinstance(result, Success)
            config = result.unwrap()

            layer = config.get_layer_config("chapter")
            assert layer.model == "claude-sonnet"
            assert layer.temperature == 0.7
            assert layer.max_tokens == 32000
            assert layer.thinking is True
            assert layer.thinking_budget == 25000
