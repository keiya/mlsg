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
    Character,
    MasterPlot,
    MPBV,
    Scene,
    StoryState,
    Stylist,
    TimelineSlice,
)
from mlsg.errors import ErrorKind, StoryError
from mlsg.layers.backstory import generate_backstories
from mlsg.layers.chapter import generate_chapter
from mlsg.layers.character import generate_characters
from mlsg.layers.mpbv import validate_mpbv
from mlsg.layers.plot import generate_master_plot
from mlsg.layers.scene import generate_scene
from mlsg.layers.stylist import generate_stylist
from mlsg.layers.timeline import generate_timeline
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
            "timeline": LayerConfig(temperature=0.3),
            "scene": LayerConfig(temperature=0.7),
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


class TestTimelineLayer:
    """Tests for the Timeline layer."""

    def test_generate_timeline_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Timeline generation should succeed with valid prerequisites."""
        client = MockLLMClient(
            responses={
                "タイムライン": """```json
{
    "時雨シン": {
        "2029-11-01 06:00": "カプセルから覚醒",
        "2029-11-01 06:30": "ラウンジで朝食"
    },
    "カナメ": {
        "2029-11-01 06:15": "意識同期事件を起こす"
    }
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
            chapters=[
                Chapter(
                    index=0,
                    title="第一章",
                    theme="目覚め",
                    chapter_beats=["覚醒", "出会い"],
                    active_characters=["時雨シン", "カナメ"],
                    is_final_chapter=False,
                    next_chapter_intent="次章へ",
                ),
            ],
        )

        result = generate_timeline(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert len(new_state.timelines) == 1
        assert new_state.timelines[0].chapter_index == 0
        assert "時雨シン" in new_state.timelines[0].characters

    def test_generate_timeline_chapter_index_preserved(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Timeline should have correct chapter_index assignment."""
        client = MockLLMClient(
            responses={
                "タイムライン": """```json
{"キャラA": {"2029-11-01 10:00": "イベント"}}
```"""
            }
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[
                Chapter(
                    index=0,
                    title="第一章",
                    theme="テーマ",
                    chapter_beats=["ビート"],
                    active_characters=[],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
                Chapter(
                    index=1,
                    title="第二章",
                    theme="テーマ2",
                    chapter_beats=["ビート2"],
                    active_characters=[],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
        )

        # Generate timeline for chapter 1 (second chapter)
        result = generate_timeline(state, client, config, prompt_loader, chapter_index=1)

        assert isinstance(result, Success)
        new_state = result.unwrap()
        timeline = new_state.get_timeline_by_chapter(1)
        assert timeline is not None
        assert timeline.chapter_index == 1

    def test_generate_timeline_missing_mpbv(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Timeline generation should fail without mpbv."""
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")

        result = generate_timeline(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE

    def test_generate_timeline_missing_chapter(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Timeline generation should fail without the target chapter."""
        client = MockLLMClient(responses={})
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[],  # No chapters
        )

        result = generate_timeline(state, client, config, prompt_loader, chapter_index=0)

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestSceneLayer:
    """Tests for the Scene layer."""

    def test_generate_scene_success(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Scene generation should succeed with valid prerequisites."""
        client = MockLLMClient(
            responses={
                "シーン": """# 本文

カプセルの蓋が開く音がした。時雨シンは目を開けた。

# 次のシーンで描くこと

シンがラウンジに向かう場面を描く。"""
            }
        )
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[
                Chapter(
                    index=0,
                    title="第一章",
                    theme="目覚め",
                    chapter_beats=["覚醒シーン", "出会いシーン"],
                    active_characters=["時雨シン"],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
            ],
            timelines=[
                TimelineSlice(
                    chapter_index=0,
                    characters={},
                ),
            ],
        )

        result = generate_scene(
            state, client, config, prompt_loader, chapter_index=0, scene_index=0
        )

        assert isinstance(result, Success)
        new_state = result.unwrap()
        assert len(new_state.scenes) == 1
        assert new_state.scenes[0].chapter_index == 0
        assert new_state.scenes[0].scene_index == 0
        assert "カプセル" in new_state.scenes[0].text

    def test_generate_scene_receives_correct_timeline(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Scene generation should receive only the timeline for its chapter."""
        # Track which timeline data was passed to the prompt
        captured_prompts: list[str] = []

        class CapturingMockClient(MockLLMClient):
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
                captured_prompts.append(prompt)
                return super().complete(
                    prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking=thinking,
                    thinking_budget=thinking_budget,
                )

        client = CapturingMockClient(
            responses={
                "シーン": """# 本文

テスト本文

# 次のシーンで描くこと

次のシーン"""
            }
        )

        # Create timelines for chapters 0 and 1 with distinct content
        from mlsg.domain import CharacterTimeline, TimelineEvent

        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[
                Chapter(
                    index=0,
                    title="第一章",
                    theme="テーマ",
                    chapter_beats=["ビート"],
                    active_characters=[],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
                Chapter(
                    index=1,
                    title="第二章",
                    theme="テーマ2",
                    chapter_beats=["ビート2"],
                    active_characters=[],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
            timelines=[
                TimelineSlice(
                    chapter_index=0,
                    characters={
                        "キャラA": CharacterTimeline(
                            character_name="キャラA",
                            events=[
                                TimelineEvent(
                                    datetime="2029-11-01 06:00",
                                    description="CHAPTER_ZERO_UNIQUE_EVENT",
                                )
                            ],
                        )
                    },
                ),
                TimelineSlice(
                    chapter_index=1,
                    characters={
                        "キャラB": CharacterTimeline(
                            character_name="キャラB",
                            events=[
                                TimelineEvent(
                                    datetime="2029-11-02 06:00",
                                    description="CHAPTER_ONE_UNIQUE_EVENT",
                                )
                            ],
                        )
                    },
                ),
            ],
        )

        # Generate scene for chapter 1
        result = generate_scene(
            state, client, config, prompt_loader, chapter_index=1, scene_index=0
        )

        assert isinstance(result, Success)
        assert len(captured_prompts) == 1

        # The prompt should contain chapter 1's timeline, not chapter 0's
        prompt = captured_prompts[0]
        assert "CHAPTER_ONE_UNIQUE_EVENT" in prompt
        assert "CHAPTER_ZERO_UNIQUE_EVENT" not in prompt

    def test_generate_scene_missing_mpbv(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Scene generation should fail without mpbv."""
        client = MockLLMClient(responses={})
        state = StoryState(seed_input="test")

        result = generate_scene(
            state, client, config, prompt_loader, chapter_index=0, scene_index=0
        )

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE

    def test_generate_scene_missing_chapter(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Scene generation should fail without the target chapter."""
        client = MockLLMClient(responses={})
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[],
        )

        result = generate_scene(
            state, client, config, prompt_loader, chapter_index=0, scene_index=0
        )

        assert isinstance(result, Failure)
        assert result.failure().kind == ErrorKind.MISSING_PREREQUISITE


class TestUserInputInPrompts:
    """Tests to verify user input is properly included in prompts."""

    def test_plot_layer_includes_seed_input(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Plot layer prompt should contain the seed input."""
        client = MockLLMClient(responses={})
        unique_seed = "UNIQUE_SEED_FOR_WIZARD_STORY_12345"
        state = StoryState(seed_input=unique_seed)

        generate_master_plot(state, client, config, prompt_loader)

        assert unique_seed in client._last_prompt

    def test_backstory_layer_includes_seed_input(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Backstory layer prompt should contain the seed input."""
        client = MockLLMClient(responses={})
        unique_seed = "UNIQUE_SEED_FOR_BACKSTORY_TEST_98765"
        unique_plot = "UNIQUE_PLOT_FOR_BACKSTORY_TEST_54321"
        state = StoryState(
            seed_input=unique_seed,
            master_plot=MasterPlot(raw_markdown=unique_plot),
        )

        generate_backstories(state, client, config, prompt_loader)

        assert unique_seed in client._last_prompt
        assert unique_plot in client._last_prompt

    def test_mpbv_layer_includes_prior_content(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """MPBV layer prompt should contain master_plot and backstories content."""
        client = MockLLMClient(responses={})
        unique_plot = "UNIQUE_PLOT_CONTENT_67890"
        unique_backstory = "UNIQUE_BACKSTORY_CONTENT_11111"
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown=unique_plot),
            backstories=Backstories(raw_markdown=unique_backstory),
        )

        validate_mpbv(state, client, config, prompt_loader)

        assert unique_plot in client._last_prompt
        assert unique_backstory in client._last_prompt

    def test_chapter_layer_includes_mpbv_content(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Chapter layer prompt should contain mpbv content."""
        client = MockLLMClient(
            responses={
                "章": """```json
{
    "chapter_title": "Test",
    "chapter_theme": "Test",
    "chapter_beats": ["beat"],
    "active_characters": [],
    "is_final_chapter": true,
    "next_chapter_intent": ""
}
```"""
            }
        )
        unique_mpbv_plot = "UNIQUE_MPBV_PLOT_22222"
        unique_mpbv_backstory = "UNIQUE_MPBV_BACKSTORY_33333"
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown=unique_mpbv_plot,
                backstories_markdown=unique_mpbv_backstory,
            ),
        )

        generate_chapter(state, client, config, prompt_loader, chapter_index=0)

        assert unique_mpbv_plot in client._last_prompt
        assert unique_mpbv_backstory in client._last_prompt

    def test_timeline_layer_includes_chapter_content(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Timeline layer prompt should contain chapter beats."""
        client = MockLLMClient(
            responses={
                "タイムライン": """```json
{"A": {"2029-01-01 00:00": "event"}}
```"""
            }
        )
        unique_chapter_title = "UNIQUE_CHAPTER_TITLE_44444"
        unique_beat = "UNIQUE_CHAPTER_BEAT_55555"
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[
                Chapter(
                    index=0,
                    title=unique_chapter_title,
                    theme="テーマ",
                    chapter_beats=[unique_beat],
                    active_characters=[],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
        )

        generate_timeline(state, client, config, prompt_loader, chapter_index=0)

        assert unique_chapter_title in client._last_prompt
        assert unique_beat in client._last_prompt

    def test_scene_layer_includes_timeline_and_chapter(
        self, config: Config, prompt_loader: PromptLoader
    ) -> None:
        """Scene layer prompt should contain timeline and chapter beat."""
        client = MockLLMClient(
            responses={
                "シーン": """# 本文

テスト

# 次のシーンで描くこと

次"""
            }
        )
        unique_beat = "UNIQUE_SCENE_BEAT_66666"
        unique_timeline_event = "UNIQUE_TIMELINE_EVENT_77777"

        from mlsg.domain import CharacterTimeline, TimelineEvent

        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
            chapters=[
                Chapter(
                    index=0,
                    title="章タイトル",
                    theme="テーマ",
                    chapter_beats=[unique_beat],
                    active_characters=[],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
            timelines=[
                TimelineSlice(
                    chapter_index=0,
                    characters={
                        "キャラ": CharacterTimeline(
                            character_name="キャラ",
                            events=[
                                TimelineEvent(
                                    datetime="2029-01-01 00:00",
                                    description=unique_timeline_event,
                                )
                            ],
                        )
                    },
                ),
            ],
        )

        generate_scene(
            state, client, config, prompt_loader, chapter_index=0, scene_index=0
        )

        assert unique_beat in client._last_prompt
        assert unique_timeline_event in client._last_prompt


class TestPromptTemplateRendering:
    """Tests for Jinja2 template rendering with max_chapters conditionals."""

    def test_plot_template_single_chapter(self, prompt_loader: PromptLoader) -> None:
        """max_chapters=1 should produce single-chapter wording."""
        result = prompt_loader.render(
            "01_master_plot.md",
            user_input="テスト",
            max_chapters=1,
        )
        assert isinstance(result, Success)
        rendered = result.unwrap()
        assert "1章構成の短編" in rendered
        assert "最大" not in rendered

    def test_plot_template_multi_chapter(self, prompt_loader: PromptLoader) -> None:
        """max_chapters>1 should produce multi-chapter wording."""
        result = prompt_loader.render(
            "01_master_plot.md",
            user_input="テスト",
            max_chapters=3,
        )
        assert isinstance(result, Success)
        rendered = result.unwrap()
        assert "最大3章" in rendered
        assert "1章構成の短編" not in rendered

    def test_chapter_template_single_chapter_no_next_intent(
        self, prompt_loader: PromptLoader
    ) -> None:
        """max_chapters=1 should omit next_chapter_intent from sample JSON."""
        result = prompt_loader.render(
            "05_chapter.md",
            n=1,
            max_chapters=1,
            previous_chapter_summary="(最初の章です)",
            previous_chapter_intent="(なし)",
        )
        assert isinstance(result, Success)
        rendered = result.unwrap()
        assert '"next_chapter_intent"' not in rendered
        assert '"is_final_chapter": true' in rendered
        assert "マスタープロットの完全消化" in rendered
        assert "Intentの継承と更新" not in rendered

    def test_chapter_template_single_chapter_json_valid(
        self, prompt_loader: PromptLoader
    ) -> None:
        """max_chapters=1 sample JSON in the template should be parseable."""
        import json
        import re

        result = prompt_loader.render(
            "05_chapter.md",
            n=1,
            max_chapters=1,
            previous_chapter_summary="(最初の章です)",
            previous_chapter_intent="(なし)",
        )
        rendered = result.unwrap()
        json_match = re.search(r"```json\s*([\s\S]*?)```", rendered)
        assert json_match is not None
        data = json.loads(json_match.group(1))
        assert data["is_final_chapter"] is True
        assert "next_chapter_intent" not in data

    def test_chapter_template_multi_chapter_has_next_intent(
        self, prompt_loader: PromptLoader
    ) -> None:
        """max_chapters>1 should include next_chapter_intent in sample JSON."""
        result = prompt_loader.render(
            "05_chapter.md",
            n=1,
            max_chapters=3,
            previous_chapter_summary="(最初の章です)",
            previous_chapter_intent="(なし)",
        )
        assert isinstance(result, Success)
        rendered = result.unwrap()
        assert "next_chapter_intent" in rendered
        assert '"is_final_chapter": false' in rendered
        assert "Intentの継承と更新" in rendered

    def test_chapter_template_multi_chapter_json_valid(
        self, prompt_loader: PromptLoader
    ) -> None:
        """max_chapters>1 sample JSON in the template should be parseable."""
        import json
        import re

        result = prompt_loader.render(
            "05_chapter.md",
            n=1,
            max_chapters=3,
            previous_chapter_summary="(最初の章です)",
            previous_chapter_intent="(なし)",
        )
        rendered = result.unwrap()
        json_match = re.search(r"```json\s*([\s\S]*?)```", rendered)
        assert json_match is not None
        data = json.loads(json_match.group(1))
        assert data["is_final_chapter"] is False
        assert "next_chapter_intent" in data


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
