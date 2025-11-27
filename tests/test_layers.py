"""Tests for story generation layers with mocked LLM client."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from returns.result import Failure, Result, Success

from mlsg.config import Config, LayerConfig
from mlsg.domain import (
    Backstories,
    Chapter,
    MasterPlot,
    MPBV,
    StoryState,
)
from mlsg.errors import ErrorKind, StoryError
from mlsg.layers.backstory import generate_backstories
from mlsg.layers.chapter import generate_chapter
from mlsg.layers.character import generate_characters
from mlsg.layers.mpbv import validate_mpbv
from mlsg.layers.plot import generate_master_plot
from mlsg.layers.stylist import generate_stylist
from mlsg.llm.prompts import PromptLoader


@dataclass
class MockLLMClient:
    """Mock LLM client for testing."""

    responses: dict[str, str]
    _call_count: int = 0
    _last_prompt: str = ""

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Result[str, StoryError]:
        self._call_count += 1
        self._last_prompt = prompt

        # Return response based on which layer is being called
        for key, response in self.responses.items():
            if key in prompt.lower():
                return Success(response)

        # Default response
        return Success("Default mock response")

    def complete_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Iterator[Result[str, StoryError]]:
        yield Success("Streamed response")


@dataclass
class FailingLLMClient:
    """Mock LLM client that always fails."""

    error_kind: ErrorKind = ErrorKind.LLM_CALL_FAILED
    error_message: str = "Mock LLM failure"

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Result[str, StoryError]:
        return Failure(StoryError(kind=self.error_kind, message=self.error_message))


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        layers={
            "plot": LayerConfig(temperature=1.0),
            "backstory": LayerConfig(temperature=1.0),
            "mpbv": LayerConfig(temperature=0.7),
            "character": LayerConfig(temperature=1.0),
            "stylist": LayerConfig(temperature=0.7),
            "chapter": LayerConfig(temperature=0.7),
        }
    )


@pytest.fixture
def prompt_loader() -> PromptLoader:
    """Create a prompt loader pointing to test prompts or real prompts."""
    # Use the actual prompts directory
    from pathlib import Path

    prompts_dir = Path(__file__).parent.parent / "prompts"
    return PromptLoader(prompts_dir)


class TestPlotLayer:
    """Tests for the Plot layer."""

    def test_generate_master_plot_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={"マスタープロット": "# Master Plot\n\nGenerated plot content"}
        )
        state = StoryState(seed_input="A story about a wizard")

        result = generate_master_plot(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.master_plot is not None
        assert "Master Plot" in new_state.master_plot.raw_markdown or len(new_state.master_plot.raw_markdown) > 0

    def test_generate_master_plot_failure(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = FailingLLMClient()
        state = StoryState(seed_input="A story")

        result = generate_master_plot(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.LLM_CALL_FAILED

    def test_generate_master_plot_preserves_seed(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="Original seed", run_name="test_run")

        result = generate_master_plot(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.seed_input == "Original seed"
        assert new_state.run_name == "test_run"


class TestBackstoryLayer:
    """Tests for the Backstory layer."""

    def test_generate_backstories_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={"世界設定": "# World Setting\n\nBackstory content"}
        )
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot"),
        )

        result = generate_backstories(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.backstories is not None

    def test_generate_backstories_missing_prerequisite(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")  # No master_plot

        result = generate_backstories(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestMPBVLayer:
    """Tests for the MPBV validation layer."""

    def test_validate_mpbv_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={
                "検証": """# Master Plot

Validated plot content

# Backstories

Validated backstory content"""
            }
        )
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Original Plot"),
            backstories=Backstories(raw_markdown="# Original Backstory"),
        )

        result = validate_mpbv(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.mpbv is not None

    def test_validate_mpbv_missing_master_plot(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(
            seed_input="test",
            backstories=Backstories(raw_markdown="# Backstory"),
        )

        result = validate_mpbv(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE

    def test_validate_mpbv_missing_backstories(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot"),
        )

        result = validate_mpbv(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestCharacterLayer:
    """Tests for the Character layer."""

    def test_generate_characters_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={
                "キャラクター": """## アリス (役割: 主人公)

キャラクター詳細...

## ボブ (役割: 敵対者)

キャラクター詳細..."""
            }
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )

        result = generate_characters(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert len(new_state.characters) > 0

    def test_generate_characters_missing_prerequisite(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")  # No MPBV

        result = generate_characters(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestStylistLayer:
    """Tests for the Stylist layer."""

    def test_generate_stylist_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={"文体": "# Style Guide\n\nWriting style details..."}
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )

        result = generate_stylist(state, client, config, prompt_loader)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.stylist is not None

    def test_generate_stylist_missing_prerequisite(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")

        result = generate_stylist(state, client, config, prompt_loader)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestChapterLayer:
    """Tests for the Chapter layer."""

    def test_generate_chapter_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={
                "章": """```json
{
    "chapter_title": "The Beginning",
    "chapter_theme": "Introduction",
    "chapter_beats": ["Hero introduced", "Call to adventure"],
    "active_characters": ["Hero"],
    "is_final_chapter": false,
    "next_chapter_intent": "Hero leaves home"
}
```"""
            }
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )

        result = generate_chapter(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert len(new_state.chapters) == 1
        assert new_state.chapters[0].title == "The Beginning"

    def test_generate_chapter_final_chapter(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(
            responses={
                "章": """```json
{
    "chapter_title": "The End",
    "chapter_theme": "Resolution",
    "chapter_beats": ["Final battle", "Victory"],
    "active_characters": ["Hero"],
    "is_final_chapter": true,
    "next_chapter_intent": ""
}
```"""
            }
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )

        result = generate_chapter(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert new_state.chapters[0].is_final_chapter is True

    def test_generate_chapter_missing_prerequisite(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")

        result = generate_chapter(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE

    def test_generate_chapter_invalid_json(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        client = MockLLMClient(responses={"章": "This is not JSON"})
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )

        result = generate_chapter(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.JSON_INVALID


class TestLayerChaining:
    """Tests for layer chaining behavior."""

    def test_state_immutability(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Ensure layers don't mutate the original state."""
        client = MockLLMClient(responses={})
        original_state = StoryState(seed_input="test")

        result = generate_master_plot(original_state, client, config, prompt_loader)

        # Original state should be unchanged
        assert original_state.master_plot is None
        if isinstance(result, Success):
            assert result.unwrap().master_plot is not None
