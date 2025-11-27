"""Tests for domain types."""

import pytest

from mlsg.domain import (
    Backstories,
    Chapter,
    Character,
    CharacterTimeline,
    MasterPlot,
    MPBV,
    Scene,
    StoryState,
    Stylist,
    TimelineEvent,
    TimelineSlice,
)


class TestStoryState:
    """Tests for StoryState."""

    def test_create_minimal_state(self) -> None:
        state = StoryState(seed_input="test seed")
        assert state.seed_input == "test seed"
        assert state.run_name == ""
        assert state.master_plot is None
        assert state.backstories is None
        assert state.mpbv is None
        assert state.characters == []
        assert state.stylist is None
        assert state.chapters == []
        assert state.timelines == []
        assert state.scenes == []

    def test_create_state_with_run_name(self) -> None:
        state = StoryState(seed_input="test", run_name="my_story")
        assert state.run_name == "my_story"

    def test_get_characters_markdown_empty(self) -> None:
        state = StoryState(seed_input="test")
        assert state.get_characters_markdown() == ""

    def test_get_characters_markdown_single(self) -> None:
        state = StoryState(
            seed_input="test",
            characters=[
                Character(name="Alice", role="protagonist", raw_markdown="# Alice\nA hero")
            ],
        )
        assert state.get_characters_markdown() == "# Alice\nA hero"

    def test_get_characters_markdown_multiple(self) -> None:
        state = StoryState(
            seed_input="test",
            characters=[
                Character(name="Alice", role="protagonist", raw_markdown="# Alice"),
                Character(name="Bob", role="antagonist", raw_markdown="# Bob"),
            ],
        )
        result = state.get_characters_markdown()
        assert "# Alice" in result
        assert "# Bob" in result
        assert "---" in result  # separator

    def test_get_chapter_by_index_found(self) -> None:
        chapter = Chapter(
            index=0,
            title="Chapter 1",
            theme="intro",
            chapter_beats=["beat1"],
            active_characters=["Alice"],
            is_final_chapter=False,
            next_chapter_intent="continue",
        )
        state = StoryState(seed_input="test", chapters=[chapter])
        found = state.get_chapter_by_index(0)
        assert found is not None
        assert found.title == "Chapter 1"

    def test_get_chapter_by_index_not_found(self) -> None:
        state = StoryState(seed_input="test")
        assert state.get_chapter_by_index(0) is None

    def test_get_chapter_by_index_multiple(self) -> None:
        chapters = [
            Chapter(
                index=i,
                title=f"Chapter {i + 1}",
                theme=f"theme{i}",
                chapter_beats=[],
                active_characters=[],
                is_final_chapter=(i == 2),
                next_chapter_intent="",
            )
            for i in range(3)
        ]
        state = StoryState(seed_input="test", chapters=chapters)
        assert state.get_chapter_by_index(1).title == "Chapter 2"
        assert state.get_chapter_by_index(2).is_final_chapter is True
        assert state.get_chapter_by_index(5) is None

    def test_get_timeline_by_chapter_found(self) -> None:
        timeline = TimelineSlice(chapter_index=0, characters={})
        state = StoryState(seed_input="test", timelines=[timeline])
        found = state.get_timeline_by_chapter(0)
        assert found is not None
        assert found.chapter_index == 0

    def test_get_timeline_by_chapter_not_found(self) -> None:
        state = StoryState(seed_input="test")
        assert state.get_timeline_by_chapter(0) is None

    def test_get_scenes_for_chapter_empty(self) -> None:
        state = StoryState(seed_input="test")
        assert state.get_scenes_for_chapter(0) == []

    def test_get_scenes_for_chapter_filters_correctly(self) -> None:
        scenes = [
            Scene(
                chapter_index=0,
                scene_index=0,
                scene_title="Scene 1",
                text="text1",
                next_scene_intent="",
                context_summary="",
                is_final_scene=False,
            ),
            Scene(
                chapter_index=0,
                scene_index=1,
                scene_title="Scene 2",
                text="text2",
                next_scene_intent="",
                context_summary="",
                is_final_scene=True,
            ),
            Scene(
                chapter_index=1,
                scene_index=0,
                scene_title="Scene 3",
                text="text3",
                next_scene_intent="",
                context_summary="",
                is_final_scene=False,
            ),
        ]
        state = StoryState(seed_input="test", scenes=scenes)
        chapter_0_scenes = state.get_scenes_for_chapter(0)
        assert len(chapter_0_scenes) == 2
        assert chapter_0_scenes[0].scene_title == "Scene 1"
        assert chapter_0_scenes[1].scene_title == "Scene 2"

        chapter_1_scenes = state.get_scenes_for_chapter(1)
        assert len(chapter_1_scenes) == 1


class TestMPBV:
    """Tests for MPBV."""

    def test_to_combined_markdown(self) -> None:
        mpbv = MPBV(
            master_plot_markdown="Plot content here",
            backstories_markdown="Backstory content here",
        )
        combined = mpbv.to_combined_markdown()
        assert "# Master Plot" in combined
        assert "Plot content here" in combined
        assert "# Backstories" in combined
        assert "Backstory content here" in combined


class TestCharacterTimeline:
    """Tests for CharacterTimeline."""

    def test_from_raw_dict(self) -> None:
        raw = {
            "2024-01-01 10:00": "Event A",
            "2024-01-01 12:00": "Event B",
        }
        timeline = CharacterTimeline.from_raw_dict("Alice", raw)
        assert timeline.character_name == "Alice"
        assert len(timeline.events) == 2

    def test_to_dict(self) -> None:
        events = [
            TimelineEvent(datetime="2024-01-01 10:00", description="Event A"),
            TimelineEvent(datetime="2024-01-01 12:00", description="Event B"),
        ]
        timeline = CharacterTimeline(character_name="Alice", events=events)
        result = timeline.to_dict()
        assert result["2024-01-01 10:00"] == "Event A"
        assert result["2024-01-01 12:00"] == "Event B"


class TestTimelineSlice:
    """Tests for TimelineSlice."""

    def test_from_raw_json(self) -> None:
        raw = {
            "Alice": {"2024-01-01 10:00": "Alice does X"},
            "Bob": {"2024-01-01 11:00": "Bob does Y"},
        }
        slice_ = TimelineSlice.from_raw_json(chapter_index=0, raw=raw)
        assert slice_.chapter_index == 0
        assert len(slice_.characters) == 2
        assert "Alice" in slice_.characters
        assert "Bob" in slice_.characters

    def test_to_dict(self) -> None:
        alice_events = [TimelineEvent(datetime="2024-01-01 10:00", description="Event")]
        slice_ = TimelineSlice(
            chapter_index=0,
            characters={
                "Alice": CharacterTimeline(character_name="Alice", events=alice_events)
            },
        )
        result = slice_.to_dict()
        assert "Alice" in result
        assert result["Alice"]["2024-01-01 10:00"] == "Event"


class TestChapter:
    """Tests for Chapter dataclass."""

    def test_chapter_creation(self) -> None:
        chapter = Chapter(
            index=0,
            title="The Beginning",
            theme="Introduction",
            chapter_beats=["Hero introduced", "Call to adventure"],
            active_characters=["Hero", "Mentor"],
            is_final_chapter=False,
            next_chapter_intent="Hero leaves home",
        )
        assert chapter.index == 0
        assert chapter.title == "The Beginning"
        assert len(chapter.chapter_beats) == 2
        assert chapter.is_final_chapter is False


class TestScene:
    """Tests for Scene dataclass."""

    def test_scene_creation(self) -> None:
        scene = Scene(
            chapter_index=0,
            scene_index=0,
            scene_title="Opening",
            text="The story begins...",
            next_scene_intent="Continue to next scene",
            context_summary="Introduction",
            is_final_scene=False,
        )
        assert scene.chapter_index == 0
        assert scene.scene_index == 0
        assert scene.is_final_scene is False
