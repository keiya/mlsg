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
from mlsg.persistence import (
    append_chapter_markdown,
    append_scene_markdown,
    export_backstory_markdown,
    export_mpbv_markdown,
    export_plot_markdown,
    export_stylist_markdown,
    from_json,
    load_external_mpbv,
    load_external_stylist,
    load_state,
    save_layer_markdown,
    save_state,
    to_json,
)


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


class TestLoadExternalMpbv:
    """Tests for load_external_mpbv function."""

    def test_load_with_both_sections(self) -> None:
        """Load MPBV with both Master Plot and Backstories sections."""
        content = """# Master Plot

## 1. Basic Info
* **Logline**: Test story

# Backstories

## 1. World Overview
* **Setting**: Fantasy world
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mpbv.md"
            path.write_text(content)

            result = load_external_mpbv(path)

            assert isinstance(result, Success)
            mpbv = result.unwrap()
            assert "Master Plot" in mpbv.master_plot_markdown
            assert "Logline" in mpbv.master_plot_markdown
            assert "Backstories" in mpbv.backstories_markdown
            assert "World Overview" in mpbv.backstories_markdown

    def test_load_without_backstories_section(self) -> None:
        """Load MPBV when Backstories section is missing."""
        content = """# Master Plot

## 1. Basic Info
* **Logline**: Test story
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mpbv.md"
            path.write_text(content)

            result = load_external_mpbv(path)

            assert isinstance(result, Success)
            mpbv = result.unwrap()
            assert "Master Plot" in mpbv.master_plot_markdown
            assert mpbv.backstories_markdown == ""

    def test_load_nonexistent_file(self) -> None:
        """Loading nonexistent file should fail."""
        result = load_external_mpbv(Path("/nonexistent/mpbv.md"))

        assert isinstance(result, Failure)
        assert "not found" in result.failure().message

    def test_case_insensitive_backstories_header(self) -> None:
        """Backstories header matching should be case-insensitive."""
        content = """# Master Plot

Content

# BACKSTORIES

More content
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mpbv.md"
            path.write_text(content)

            result = load_external_mpbv(path)

            assert isinstance(result, Success)
            mpbv = result.unwrap()
            assert "BACKSTORIES" in mpbv.backstories_markdown


class TestLoadExternalStylist:
    """Tests for load_external_stylist function."""

    def test_load_stylist(self) -> None:
        """Load Stylist from markdown file."""
        content = """# Style Guide

## Author Persona
* 村上春樹風の文体

## Prohibited
* 過度な説明
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stylist.md"
            path.write_text(content)

            result = load_external_stylist(path)

            assert isinstance(result, Success)
            stylist = result.unwrap()
            assert "Style Guide" in stylist.raw_markdown
            assert "村上春樹" in stylist.raw_markdown
            assert "過度な説明" in stylist.raw_markdown

    def test_load_nonexistent_file(self) -> None:
        """Loading nonexistent file should fail."""
        result = load_external_stylist(Path("/nonexistent/stylist.md"))

        assert isinstance(result, Failure)
        assert "not found" in result.failure().message

    def test_strips_whitespace(self) -> None:
        """Content should be stripped of leading/trailing whitespace."""
        content = """

# Style Guide

Content here

"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stylist.md"
            path.write_text(content)

            result = load_external_stylist(path)

            assert isinstance(result, Success)
            stylist = result.unwrap()
            assert stylist.raw_markdown.startswith("# Style Guide")
            assert stylist.raw_markdown.endswith("Content here")


class TestSaveLayerMarkdown:
    """Tests for save_layer_markdown function."""

    def test_save_overwrites_by_default(self) -> None:
        """Default mode should overwrite the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            
            save_layer_markdown(runs_dir, "test.md", "First content")
            save_layer_markdown(runs_dir, "test.md", "Second content")
            
            content = (runs_dir / "test.md").read_text()
            assert content == "Second content"

    def test_save_appends_when_requested(self) -> None:
        """Append mode should add to existing content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            
            save_layer_markdown(runs_dir, "test.md", "First\n", append=False)
            save_layer_markdown(runs_dir, "test.md", "Second\n", append=True)
            save_layer_markdown(runs_dir, "test.md", "Third", append=True)
            
            content = (runs_dir / "test.md").read_text()
            assert "First" in content
            assert "Second" in content
            assert "Third" in content

    def test_append_adds_newline_if_missing(self) -> None:
        """Append mode should add trailing newline if content doesn't end with one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            
            save_layer_markdown(runs_dir, "test.md", "Line1", append=False)
            save_layer_markdown(runs_dir, "test.md", "Line2", append=True)
            
            content = (runs_dir / "test.md").read_text()
            # Line2 should be on its own line due to added newline
            assert content == "Line1Line2\n"


class TestExportMarkdownFunctions:
    """Tests for individual export functions."""

    def test_export_plot_markdown(self) -> None:
        """Export plot should create 01_plot.md."""
        state = StoryState(
            seed_input="test",
            master_plot=MasterPlot(raw_markdown="# Master Plot\n\nContent here"),
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = export_plot_markdown(state, runs_dir)
            
            assert isinstance(result, Success)
            assert (runs_dir / "01_plot.md").exists()
            content = (runs_dir / "01_plot.md").read_text()
            assert "Master Plot" in content

    def test_export_plot_markdown_skips_if_none(self) -> None:
        """Export should succeed but do nothing if master_plot is None."""
        state = StoryState(seed_input="test")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = export_plot_markdown(state, runs_dir)
            
            assert isinstance(result, Success)
            assert not (runs_dir / "01_plot.md").exists()

    def test_export_backstory_markdown(self) -> None:
        """Export backstory should create 02_backstory.md."""
        state = StoryState(
            seed_input="test",
            backstories=Backstories(raw_markdown="# Backstories\n\nWorld details"),
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = export_backstory_markdown(state, runs_dir)
            
            assert isinstance(result, Success)
            assert (runs_dir / "02_backstory.md").exists()
            content = (runs_dir / "02_backstory.md").read_text()
            assert "Backstories" in content

    def test_export_mpbv_markdown(self) -> None:
        """Export mpbv should create 03_mpbv.md with both sections."""
        state = StoryState(
            seed_input="test",
            mpbv=MPBV(
                master_plot_markdown="# Master Plot\n\nPlot content",
                backstories_markdown="# Backstories\n\nBackstory content",
            ),
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = export_mpbv_markdown(state, runs_dir)
            
            assert isinstance(result, Success)
            assert (runs_dir / "03_mpbv.md").exists()
            content = (runs_dir / "03_mpbv.md").read_text()
            assert "Master Plot" in content
            assert "Backstories" in content
            assert "---" in content  # Separator

    def test_export_stylist_markdown(self) -> None:
        """Export stylist should create 05_stylist.md."""
        state = StoryState(
            seed_input="test",
            stylist=Stylist(raw_markdown="# Style Guide\n\nWriting style"),
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = export_stylist_markdown(state, runs_dir)
            
            assert isinstance(result, Success)
            assert (runs_dir / "05_stylist.md").exists()
            content = (runs_dir / "05_stylist.md").read_text()
            assert "Style Guide" in content


class TestAppendMarkdownFunctions:
    """Tests for append functions (chapters and scenes)."""

    def test_append_chapter_markdown(self) -> None:
        """Append chapter should add to 06_chapters.md."""
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="始まりの章",
                    theme="出会い",
                    chapter_beats=["ビート1", "ビート2"],
                    active_characters=["主人公", "ヒロイン"],
                    is_final_chapter=False,
                    next_chapter_intent="次へ",
                ),
            ],
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = append_chapter_markdown(state, runs_dir, 0)
            
            assert isinstance(result, Success)
            assert (runs_dir / "06_chapters.md").exists()
            content = (runs_dir / "06_chapters.md").read_text()
            assert "第1章" in content
            assert "始まりの章" in content
            assert "出会い" in content
            assert "ビート1" in content
            assert "主人公" in content

    def test_append_chapter_markdown_multiple(self) -> None:
        """Multiple chapters should be appended sequentially."""
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="第一章タイトル",
                    theme="テーマ1",
                    chapter_beats=["ビート"],
                    active_characters=[],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
                Chapter(
                    index=1,
                    title="第二章タイトル",
                    theme="テーマ2",
                    chapter_beats=["ビート"],
                    active_characters=[],
                    is_final_chapter=True,
                    next_chapter_intent="",
                ),
            ],
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            append_chapter_markdown(state, runs_dir, 0)
            append_chapter_markdown(state, runs_dir, 1)
            
            content = (runs_dir / "06_chapters.md").read_text()
            assert "第1章" in content
            assert "第一章タイトル" in content
            assert "第2章" in content
            assert "第二章タイトル" in content
            assert "最終章" in content

    def test_append_scene_markdown(self) -> None:
        """Append scene should add to 08_scenes.md."""
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="章タイトル",
                    theme="テーマ",
                    chapter_beats=[],
                    active_characters=[],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
            ],
            scenes=[
                Scene(
                    chapter_index=0,
                    scene_index=0,
                    scene_title="シーン1",
                    text="物語の本文がここに入ります。\n\n段落も含まれます。",
                    next_scene_intent="次のシーン",
                    is_final_scene=False,
                ),
            ],
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            result = append_scene_markdown(state, runs_dir, 0, 0)
            
            assert isinstance(result, Success)
            assert (runs_dir / "08_scenes.md").exists()
            content = (runs_dir / "08_scenes.md").read_text()
            assert "第1章" in content
            assert "シーン1" in content
            assert "物語の本文" in content
            assert "章タイトル" in content

    def test_append_scene_markdown_multiple(self) -> None:
        """Multiple scenes should be appended sequentially for tail -f."""
        state = StoryState(
            seed_input="test",
            chapters=[
                Chapter(
                    index=0,
                    title="章",
                    theme="テーマ",
                    chapter_beats=[],
                    active_characters=[],
                    is_final_chapter=False,
                    next_chapter_intent="",
                ),
            ],
            scenes=[
                Scene(
                    chapter_index=0,
                    scene_index=0,
                    scene_title="シーン1",
                    text="SCENE_ONE_CONTENT",
                    next_scene_intent="",
                    is_final_scene=False,
                ),
                Scene(
                    chapter_index=0,
                    scene_index=1,
                    scene_title="シーン2",
                    text="SCENE_TWO_CONTENT",
                    next_scene_intent="",
                    is_final_scene=True,
                ),
            ],
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            append_scene_markdown(state, runs_dir, 0, 0)
            append_scene_markdown(state, runs_dir, 0, 1)
            
            content = (runs_dir / "08_scenes.md").read_text()
            # Both scenes should be present
            assert "SCENE_ONE_CONTENT" in content
            assert "SCENE_TWO_CONTENT" in content
            # First scene should come before second (order preserved)
            assert content.index("SCENE_ONE") < content.index("SCENE_TWO")
