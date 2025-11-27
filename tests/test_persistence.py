"""Tests for persistence layer."""

import json
import tempfile
from pathlib import Path

import pytest
from returns.result import Failure, Success

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
from mlsg.persistence import from_json, load_state, save_state, to_json


class TestToJson:
    """Tests for to_json serialization."""

    def test_minimal_state(self) -> None:
        state = StoryState(seed_input="test seed", run_name="test_run")
        json_str = to_json(state)
        data = json.loads(json_str)

        assert data["seed_input"] == "test seed"
        assert data["run_name"] == "test_run"
        assert "master_plot" not in data
        assert "backstories" not in data

    def test_state_with_master_plot(self) -> None:
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Plot\nContent here"),
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "master_plot" in data
        assert data["master_plot"]["raw_markdown"] == "# Plot\nContent here"

    def test_state_with_backstories(self) -> None:
        state = StoryState(
            seed_input="test",
            backstories=Backstories(raw_markdown="# World\nBackstory content"),
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "backstories" in data
        assert data["backstories"]["raw_markdown"] == "# World\nBackstory content"

    def test_state_with_mpbv(self) -> None:
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Plot",
                backstories_markdown="# Backstory",
            ),
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "mpbv" in data
        assert data["mpbv"]["master_plot_markdown"] == "# Plot"
        assert data["mpbv"]["backstories_markdown"] == "# Backstory"

    def test_state_with_characters(self) -> None:
        state = StoryState(
            seed_input="test",
            characters=[
                Character(name="Alice", role="protagonist", raw_markdown="# Alice"),
                Character(name="Bob", role="antagonist", raw_markdown="# Bob"),
            ],
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "characters" in data
        assert len(data["characters"]) == 2
        assert data["characters"][0]["name"] == "Alice"
        assert data["characters"][1]["name"] == "Bob"

    def test_state_with_stylist(self) -> None:
        state = StoryState(
            seed_input="test",
            stylist=Stylist(raw_markdown="# Style Guide"),
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "stylist" in data
        assert data["stylist"]["raw_markdown"] == "# Style Guide"

    def test_state_with_chapters(self) -> None:
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="Chapter 1",
                    theme="Introduction",
                    chapter_beats=["beat1", "beat2"],
                    active_characters=["Alice"],
                    is_final_chapter=False,
                    next_chapter_intent="Continue",
                ),
            ],
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "chapters" in data
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["title"] == "Chapter 1"
        assert data["chapters"][0]["chapter_beats"] == ["beat1", "beat2"]

    def test_state_with_timelines(self) -> None:
        events = [TimelineEvent(datetime="2024-01-01 10:00", description="Event")]
        timeline = TimelineSlice(
            chapter_index=0,
            characters={
                "Alice": CharacterTimeline(character_name="Alice", events=events)
            },
        )
        state = StoryState(seed_input="test", timelines=[timeline])
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "timelines" in data
        assert len(data["timelines"]) == 1
        assert data["timelines"][0]["chapter_index"] == 0

    def test_state_with_scenes(self) -> None:
        state = StoryState(
            seed_input="test",
            scenes=[
                Scene(
                    chapter_index=0,
                    scene_index=0,
                    scene_title="Scene 1",
                    text="The story begins...",
                    next_scene_intent="Continue",
                    context_summary="Opening",
                    is_final_scene=False,
                ),
            ],
        )
        json_str = to_json(state)
        data = json.loads(json_str)

        assert "scenes" in data
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["text"] == "The story begins..."


class TestFromJson:
    """Tests for from_json deserialization."""

    def test_minimal_state(self) -> None:
        json_str = '{"seed_input": "test", "run_name": "my_run"}'
        result = from_json(json_str)

        assert isinstance(result, Success)
        state = result.unwrap()
        assert state.seed_input == "test"
        assert state.run_name == "my_run"

    def test_invalid_json(self) -> None:
        result = from_json("not valid json")
        assert isinstance(result, Failure)
        assert "Invalid JSON" in result.failure().message

    def test_missing_required_field(self) -> None:
        result = from_json('{"run_name": "test"}')  # missing seed_input
        assert isinstance(result, Failure)

    def test_full_roundtrip(self) -> None:
        """Test that serialization and deserialization are inverse operations."""
        original = StoryState(
            seed_input="test seed",
            run_name="test_run",
            master_plot=MasterPlot(raw_markdown="# Plot"),
            backstories=Backstories(raw_markdown="# Backstory"),
            mpbv=MPBV(
                master_plot_markdown="# Validated Plot",
                backstories_markdown="# Validated Backstory",
            ),
            characters=[
                Character(name="Alice", role="protagonist", raw_markdown="# Alice"),
            ],
            stylist=Stylist(raw_markdown="# Style"),
            chapters=[
                Chapter(
                    index=0,
                    title="Chapter 1",
                    theme="Intro",
                    chapter_beats=["beat1"],
                    active_characters=["Alice"],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
            scenes=[
                Scene(
                    chapter_index=0,
                    scene_index=0,
                    scene_title="Scene 1",
                    text="Content",
                    next_scene_intent="",
                    context_summary="Summary",
                    is_final_scene=True,
                ),
            ],
        )

        # Serialize and deserialize
        json_str = to_json(original)
        result = from_json(json_str)

        assert isinstance(result, Success)
        restored = result.unwrap()

        # Verify all fields
        assert restored.seed_input == original.seed_input
        assert restored.run_name == original.run_name
        assert restored.master_plot.raw_markdown == original.master_plot.raw_markdown
        assert restored.backstories.raw_markdown == original.backstories.raw_markdown
        assert restored.mpbv.master_plot_markdown == original.mpbv.master_plot_markdown
        assert len(restored.characters) == 1
        assert restored.characters[0].name == "Alice"
        assert restored.stylist.raw_markdown == original.stylist.raw_markdown
        assert len(restored.chapters) == 1
        assert restored.chapters[0].title == "Chapter 1"
        assert len(restored.scenes) == 1
        assert restored.scenes[0].text == "Content"

    def test_roundtrip_with_timelines(self) -> None:
        """Test timeline serialization roundtrip."""
        events = [
            TimelineEvent(datetime="2024-01-01 10:00", description="Event A"),
            TimelineEvent(datetime="2024-01-01 12:00", description="Event B"),
        ]
        original = StoryState(
            seed_input="test",
            timelines=[
                TimelineSlice(
                    chapter_index=0,
                    characters={
                        "Alice": CharacterTimeline(character_name="Alice", events=events)
                    },
                )
            ],
        )

        json_str = to_json(original)
        result = from_json(json_str)

        assert isinstance(result, Success)
        restored = result.unwrap()
        assert len(restored.timelines) == 1
        assert restored.timelines[0].chapter_index == 0
        assert "Alice" in restored.timelines[0].characters
        assert len(restored.timelines[0].characters["Alice"].events) == 2


class TestSaveAndLoadState:
    """Tests for file-based save and load operations."""

    def test_save_and_load_roundtrip(self) -> None:
        state = StoryState(
            seed_input="test seed",
            run_name="test_run",
            master_plot=MasterPlot(raw_markdown="# Plot"),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"

            # Save
            save_result = save_state(state, path)
            assert isinstance(save_result, Success)
            assert path.exists()

            # Load
            load_result = load_state(path)
            assert isinstance(load_result, Success)
            loaded = load_result.unwrap()

            assert loaded.seed_input == state.seed_input
            assert loaded.run_name == state.run_name
            assert loaded.master_plot.raw_markdown == state.master_plot.raw_markdown

    def test_load_nonexistent_file(self) -> None:
        result = load_state(Path("/nonexistent/path/state.json"))
        assert isinstance(result, Failure)
        assert "not found" in result.failure().message

    def test_save_creates_parent_directories(self) -> None:
        state = StoryState(seed_input="test")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "state.json"

            save_result = save_state(state, path)
            assert isinstance(save_result, Success)
            assert path.exists()

    def test_json_is_human_readable(self) -> None:
        """Ensure saved JSON is indented and readable."""
        state = StoryState(seed_input="test", run_name="my_run")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            save_state(state, path)

            content = path.read_text()
            # Should be indented (multiple lines)
            assert content.count("\n") > 1
            # Should contain Japanese without escaping
            # (ensure_ascii=False in to_json)
