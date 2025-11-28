from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MasterPlot:
    """Raw master plot output from the Plot Layer."""

    raw_markdown: str


@dataclass(slots=True)
class Backstories:
    """Raw backstories output from the Backstory Layer."""

    raw_markdown: str


@dataclass(slots=True)
class MPBV:
    """Validated master plot + backstories (Master Plot & Backstory Validated).

    This is the unified, conflict-resolved version produced by the MPBV layer.
    """

    master_plot_markdown: str
    backstories_markdown: str

    def to_combined_markdown(self) -> str:
        """Combine master plot and backstories into a single markdown string."""
        return f"# Master Plot\n\n{self.master_plot_markdown}\n\n# Backstories\n\n{self.backstories_markdown}"


@dataclass(slots=True)
class Character:
    """A character definition from the Character Layer."""

    name: str
    role: str
    raw_markdown: str


@dataclass(slots=True)
class Stylist:
    """Writer persona and style guidelines from the Stylist Layer."""

    raw_markdown: str


@dataclass(slots=True)
class Chapter:
    """Chapter structure from the Chapter Layer.

    Corresponds to the JSON output format of prompts/05_chapter.md.
    """

    index: int
    title: str
    theme: str
    chapter_beats: list[str]
    active_characters: list[str]
    is_final_chapter: bool
    next_chapter_intent: str


@dataclass(slots=True)
class TimelineEvent:
    """A single event in a character's timeline.

    The datetime format is "YYYY-MM-DD HH:MM" as specified in the
    Timeline Layer prompt.
    """

    datetime: str
    description: str


@dataclass(slots=True)
class CharacterTimeline:
    """Timeline events for a single character within a chapter."""

    character_name: str
    events: list[TimelineEvent]

    @classmethod
    def from_raw_dict(
        cls, character_name: str, events_dict: dict[str, str]
    ) -> CharacterTimeline:
        """Create from the raw JSON format: {"YYYY-MM-DD HH:MM": "description"}."""
        events = [
            TimelineEvent(datetime=dt, description=desc)
            for dt, desc in events_dict.items()
        ]
        return cls(character_name=character_name, events=events)

    def to_dict(self) -> dict[str, str]:
        """Convert back to the raw JSON format."""
        return {event.datetime: event.description for event in self.events}


@dataclass(slots=True)
class TimelineSlice:
    """Timeline information for a single chapter.

    Contains all character timelines extracted from that chapter.
    This is the structured representation of the Timeline Layer output.
    """

    chapter_index: int
    characters: dict[str, CharacterTimeline]

    @classmethod
    def from_raw_json(
        cls, chapter_index: int, raw: dict[str, dict[str, str]]
    ) -> TimelineSlice:
        """Create from the raw JSON format produced by the Timeline Layer.

        Expected format:
        {
            "Character_A": {"YYYY-MM-DD HH:MM": "event description", ...},
            "Character_B": {...}
        }
        """
        characters = {
            name: CharacterTimeline.from_raw_dict(name, events)
            for name, events in raw.items()
        }
        return cls(chapter_index=chapter_index, characters=characters)

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Convert back to the raw JSON format."""
        return {name: timeline.to_dict() for name, timeline in self.characters.items()}


@dataclass(slots=True)
class Scene:
    """A scene (merged Section + Paragraph) from the Scene Layer.

    Corresponds to the output format of prompts/08_scene.md.
    """

    chapter_index: int
    scene_index: int
    scene_title: str
    text: str
    next_scene_intent: str
    is_final_scene: bool


@dataclass(slots=True)
class StoryState:
    """Central state object shared across all layers.

    Each generator step receives a StoryState and returns a new one,
    possibly wrapped in a Result for explicit error handling.
    """

    seed_input: str
    run_name: str = ""
    master_plot: MasterPlot | None = None
    backstories: Backstories | None = None
    mpbv: MPBV | None = None
    characters: list[Character] = field(default_factory=list)
    stylist: Stylist | None = None
    chapters: list[Chapter] = field(default_factory=list)
    timelines: list[TimelineSlice] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)

    def get_characters_markdown(self) -> str:
        """Get all characters as a combined markdown string."""
        if not self.characters:
            return ""
        parts = [char.raw_markdown for char in self.characters]
        return "\n\n---\n\n".join(parts)

    def get_chapter_by_index(self, index: int) -> Chapter | None:
        """Get a chapter by its index."""
        for chapter in self.chapters:
            if chapter.index == index:
                return chapter
        return None

    def get_timeline_by_chapter(self, chapter_index: int) -> TimelineSlice | None:
        """Get timeline for a specific chapter."""
        for timeline in self.timelines:
            if timeline.chapter_index == chapter_index:
                return timeline
        return None

    def get_scenes_for_chapter(self, chapter_index: int) -> list[Scene]:
        """Get all scenes for a specific chapter."""
        return [s for s in self.scenes if s.chapter_index == chapter_index]


__all__ = [
    "Backstories",
    "Chapter",
    "Character",
    "CharacterTimeline",
    "MPBV",
    "MasterPlot",
    "Scene",
    "StoryState",
    "Stylist",
    "TimelineEvent",
    "TimelineSlice",
]
