"""Tests for pipeline orchestration and resume functionality."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from returns.result import Result, Success

from mlsg.config import Config, LayerConfig
from mlsg.domain import (
    Backstories,
    Chapter,
    Character,
    MasterPlot,
    MPBV,
    Scene,
    StoryState,
    Stylist,
    TimelineSlice,
)
from mlsg.errors import StoryError
from mlsg.llm.prompts import PromptLoader
from mlsg.pipeline import _is_layer_completed, run_pipeline


@dataclass
class MockLLMClient:
    """Mock LLM client for testing.

    Keys in responses dict are matched against the start of prompts to
    identify which layer is being called. Use template-specific markers.
    """

    responses: dict[str, str]
    call_log: list[str] | None = None

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []

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
        # Match based on unique markers at the start of each template
        # plot: starts with "# マスタープロット生成"
        # backstory: starts with "# 世界設定生成"
        # mpbv: starts with "# マスタープロットと世界設定の検証"

        matched_key: str | None = None
        for key in self.responses:
            if prompt.startswith(key):
                matched_key = key
                break

        if matched_key and self.call_log is not None:
            self.call_log.append(matched_key)

        if matched_key:
            return Success(self.responses[matched_key])

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
            "timeline": LayerConfig(temperature=0.3),
            "scene": LayerConfig(temperature=0.7),
        }
    )


@pytest.fixture
def prompt_loader() -> PromptLoader:
    """Create a prompt loader."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    return PromptLoader(prompts_dir)


class TestIsLayerCompleted:
    """Tests for _is_layer_completed helper function."""

    def test_plot_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "plot") is False

    def test_plot_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot"),
        )
        assert _is_layer_completed(state, "plot") is True

    def test_backstory_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "backstory") is False

    def test_backstory_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            backstories=Backstories(raw_markdown="# Backstory"),
        )
        assert _is_layer_completed(state, "backstory") is True

    def test_mpbv_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "mpbv") is False

    def test_mpbv_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )
        assert _is_layer_completed(state, "mpbv") is True

    def test_character_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "character") is False

    def test_character_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            characters=[Character(name="Test", role="主人公", raw_markdown="# Char")],
        )
        assert _is_layer_completed(state, "character") is True

    def test_stylist_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "stylist") is False

    def test_stylist_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            stylist=Stylist(raw_markdown="# Style"),
        )
        assert _is_layer_completed(state, "stylist") is True

    def test_chapter_not_completed_empty(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "chapter") is False

    def test_chapter_not_completed_no_final(self) -> None:
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="Ch1",
                    theme="テーマ",
                    chapter_beats=["Beat 1"],
                    active_characters=["主人公"],
                    is_final_chapter=False,
                    next_chapter_intent="次章への伏線",
                )
            ],
        )
        assert _is_layer_completed(state, "chapter") is False

    def test_chapter_completed_with_final(self) -> None:
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="Ch1",
                    theme="テーマ",
                    chapter_beats=["Beat 1"],
                    active_characters=["主人公"],
                    is_final_chapter=True,
                    next_chapter_intent="",
                )
            ],
        )
        assert _is_layer_completed(state, "chapter") is True

    def test_timeline_not_completed_no_chapters(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "timeline") is False

    def test_timeline_not_completed_missing_timelines(self) -> None:
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="Ch1",
                    theme="テーマ",
                    chapter_beats=["Beat 1"],
                    active_characters=["主人公"],
                    is_final_chapter=True,
                    next_chapter_intent="",
                )
            ],
            timelines=[],
        )
        assert _is_layer_completed(state, "timeline") is False

    def test_timeline_completed(self) -> None:
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="Ch1",
                    theme="テーマ",
                    chapter_beats=["Beat 1"],
                    active_characters=["主人公"],
                    is_final_chapter=True,
                    next_chapter_intent="",
                )
            ],
            timelines=[
                TimelineSlice(chapter_index=0, characters={}),
            ],
        )
        assert _is_layer_completed(state, "timeline") is True

    def test_scene_not_completed(self) -> None:
        state = StoryState(seed_input="test")
        assert _is_layer_completed(state, "scene") is False

    def test_scene_completed_with_final(self) -> None:
        state = StoryState(
            seed_input="test",
            scenes=[
                Scene(
                    chapter_index=0,
                    scene_index=0,
                    scene_title="Scene 1",
                    text="Scene text",
                    next_scene_intent="",
                    context_summary="Summary",
                    is_final_scene=True,
                ),
            ],
        )
        assert _is_layer_completed(state, "scene") is True


class TestPipelineResume:
    """Tests for pipeline resume functionality.

    Note: These tests use a LayerTrackingClient that tracks which layers
    are called based on prompt content detection.
    """

    def test_skips_completed_plot_layer(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Pipeline should skip plot layer if master_plot already exists."""
        layers_called: list[str] = []

        @dataclass
        class LayerTrackingClient:
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
                # Detect layer based on unique template content
                if "「マスタープロット」を作成" in prompt and "世界設定構築者" not in prompt:
                    layers_called.append("plot")
                elif "世界設定構築者" in prompt:
                    layers_called.append("backstory")
                return Success("# Response")

        # State with plot already completed
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Existing Plot"),
        )

        result = run_pipeline(
            state,
            LayerTrackingClient(),
            config,
            prompt_loader,
            until="backstory",
        )

        assert isinstance(result, Success)
        # Should only call backstory, not plot
        assert "plot" not in layers_called
        assert "backstory" in layers_called

    def test_skips_completed_plot_and_backstory(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Pipeline should skip both plot and backstory if already completed."""
        layers_called: list[str] = []

        mpbv_response = """# Master Plot

Validated plot content here.

# Backstories

Validated backstory content here."""

        @dataclass
        class LayerTrackingClient:
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
                # Detect layer based on unique template content
                if "「マスタープロット」を作成" in prompt and "論理的矛盾を検証" not in prompt:
                    layers_called.append("plot")
                    return Success("# Plot")
                elif "世界設定構築者" in prompt:
                    layers_called.append("backstory")
                    return Success("# Backstory")
                elif "論理的矛盾を検証" in prompt:
                    layers_called.append("mpbv")
                    return Success(mpbv_response)
                return Success("# Response")

        # State with plot and backstory already completed
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Existing Plot"),
            backstories=Backstories(raw_markdown="# Existing Backstory"),
        )

        result = run_pipeline(
            state,
            LayerTrackingClient(),
            config,
            prompt_loader,
            until="mpbv",
        )

        assert isinstance(result, Success)
        # Should only call mpbv, not plot or backstory
        assert "plot" not in layers_called
        assert "backstory" not in layers_called
        assert "mpbv" in layers_called

    def test_resumes_from_partial_state(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Pipeline should resume from where it left off."""
        layers_called: list[str] = []

        @dataclass
        class LayerTrackingClient:
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
                if "「マスタープロット」を作成" in prompt and "世界設定構築者" not in prompt:
                    layers_called.append("plot")
                elif "世界設定構築者" in prompt:
                    layers_called.append("backstory")
                return Success("# Response")

        # Fresh state - nothing completed
        state = StoryState(seed_input="test")

        result = run_pipeline(
            state,
            LayerTrackingClient(),
            config,
            prompt_loader,
            until="backstory",
        )

        assert isinstance(result, Success)
        # Should call both layers
        assert "plot" in layers_called
        assert "backstory" in layers_called
        assert len(layers_called) == 2

    def test_only_option_skips_completed(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """When using --only, should still check completion and skip."""
        layers_called: list[str] = []

        @dataclass
        class LayerTrackingClient:
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
                if "世界設定構築者" in prompt:
                    layers_called.append("backstory")
                return Success("# Response")

        # State with backstory already completed
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot"),
            backstories=Backstories(raw_markdown="# Existing Backstory"),
        )

        result = run_pipeline(
            state,
            LayerTrackingClient(),
            config,
            prompt_loader,
            only="backstory",
        )

        assert isinstance(result, Success)
        # With only=backstory, since it's completed, should skip
        assert "backstory" not in layers_called

    def test_all_layers_completed_does_nothing(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Pipeline should do nothing if all requested layers are completed."""
        layers_called: list[str] = []

        @dataclass
        class LayerTrackingClient:
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
                layers_called.append("any")
                return Success("# Response")

        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot"),
            backstories=Backstories(raw_markdown="# Backstory"),
        )

        result = run_pipeline(
            state,
            LayerTrackingClient(),
            config,
            prompt_loader,
            until="backstory",
        )

        assert isinstance(result, Success)
        # No LLM calls should be made
        assert len(layers_called) == 0
