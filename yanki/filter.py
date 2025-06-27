from dataclasses import dataclass
from typing import Set, Generator
import functools
import click
import asyncio

from yanki.anki import Deck
from yanki.parser import DeckFilesParser, DeckSpec, NoteSpec
from yanki.video import VideoOptions


@dataclass(frozen=True)
class DeckFilter:
    """Filter notes in decks."""

    tags_include: Set[str] = frozenset()
    tags_exclude: Set[str] = frozenset()

    def _include_note(self, note_spec: NoteSpec) -> bool:
        """Check if a note should be included based on tag filters."""
        tags = note_spec.config.tags
        # fmt: off
        return (
            self.tags_include.issubset(tags)
            and self.tags_exclude.isdisjoint(tags)
        )

    def filter(self, deck_spec: DeckSpec) -> Generator:
        """Filter notes in decks, only yielding decks that still have notes."""
        filtered = []
        for note_spec in deck_spec.note_specs:
            if self._include_note(note_spec):
                filtered.append(note_spec)

        if filtered:
            deck_spec.note_specs = filtered
            yield deck_spec

    def __str__(self) -> str:
        """Human-readable string representation."""
        parts = []
        if self.tags_include:
            parts.append(f"tags_include={sorted(self.tags_include)}")
        if self.tags_exclude:
            parts.append(f"tags_exclude={sorted(self.tags_exclude)}")
        return f"DeckFilter({', '.join(parts) if parts else 'no filters'})"


def filter_options(func):
    """
    Decorator that adds tag filtering options to a Click command.

    Adds the following options:
    - -i/--include-tag: Only include notes that have all specified tags
    - -x/--exclude-tag: Exclude notes that have any of the specified tags

    The decorator creates a DeckFilter instance and passes it as the 'filter'
    parameter.
    """

    @click.option(
        "-i",
        "--include-tag",
        multiple=True,
        default=[],
        metavar="TAG",
        help="Only include notes that have tag TAG. If specified multiple times, "
        "notes must have all TAGs.",
    )
    @click.option(
        "-x",
        "--exclude-tag",
        multiple=True,
        default=[],
        metavar="TAG",
        help="Exclude notes that have tag TAG. If specified multiple times, "
        "notes with any tag in TAGs will be excluded.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Create DeckFilter from the tag options
        kwargs["filter"] = DeckFilter(
            tags_include=frozenset(kwargs.pop("include_tag")),
            tags_exclude=frozenset(kwargs.pop("exclude_tag")),
        )

        return func(*args, **kwargs)

    return wrapper


def read_deck_specs(files, filter=DeckFilter()):
    """Read `DeckSpec`s from `files`."""
    parser = DeckFilesParser()
    for file in files:
        for deck_spec in parser.parse_file(file.name, file):
            for deck_spec in filter.filter(deck_spec):
                yield deck_spec


def read_decks(files, options: VideoOptions, filter=DeckFilter()):
    """Read `Deck`s from `files`."""
    for spec in read_deck_specs(files, filter):
        yield Deck(spec, video_options=options)


def read_decks_sorted(files, options: VideoOptions, filter=DeckFilter()):
    """Read `Deck`s from `files` and return them sorted by title."""
    return sorted(
        read_decks(files, options, filter), key=lambda deck: deck.title()
    )


async def read_final_decks_async(
    files, options: VideoOptions, filter=DeckFilter()
):
    """Read `FinalDeck`s from `files` (async)."""

    async def finalize_deck_async(collection, deck):
        collection.append(await deck.finalize_async())

    final_decks = []
    async with asyncio.TaskGroup() as group:
        for deck in read_decks(files, options, filter):
            group.create_task(finalize_deck_async(final_decks, deck))

    return final_decks


def read_final_decks(files, options: VideoOptions, filter=DeckFilter()):
    """Read `FinalDeck`s from `files`."""
    return asyncio.run(read_final_decks_async(files, options, filter))


def read_final_decks_sorted(files, options: VideoOptions, filter=DeckFilter()):
    """Read `FinalDeck`s from `files` and return them sorted by title."""
    return sorted(
        read_final_decks(files, options, filter), key=lambda deck: deck.title
    )
