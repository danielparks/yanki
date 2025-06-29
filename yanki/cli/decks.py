import asyncio
import functools
from collections.abc import Generator
from dataclasses import dataclass

import click

from yanki.anki import Deck
from yanki.parser import DeckFilesParser, DeckSpec, NoteSpec
from yanki.video import VideoOptions


@dataclass(frozen=True)
class DeckSource:
    """Filter notes in decks."""

    files: list[click.File]
    tags_include: set[str] = frozenset()
    tags_exclude: set[str] = frozenset()

    def _include_note(self, note_spec: NoteSpec) -> bool:
        """Check if a note should be included based on tag filters."""
        tags = note_spec.config.tags
        # fmt: off
        return (
            self.tags_include.issubset(tags)
            and self.tags_exclude.isdisjoint(tags)
        )

    def filter_deck_spec(self, deck_spec: DeckSpec) -> Generator[DeckSpec]:
        """Filter notes in decks, only yielding decks that still have notes."""
        filtered = [
            note_spec
            for note_spec in deck_spec.note_specs
            if self._include_note(note_spec)
        ]

        if filtered:
            deck_spec.note_specs = filtered
            yield deck_spec

    def read_specs(self):
        """Read `DeckSpec`s from `files`."""
        parser = DeckFilesParser()
        for file in self.files:
            for deck_spec in parser.parse_file(file.name, file):
                yield from self.filter_deck_spec(deck_spec)

    def read(self, options: VideoOptions):
        """Read `Deck`s from `self.files`."""
        for spec in self.read_specs():
            yield Deck(spec, video_options=options)

    def read_sorted(self, options: VideoOptions):
        """Read `Deck`s from `self.files` and sort by title."""
        return sorted(self.read(options), key=lambda deck: deck.title())

    async def read_final_async(self, options: VideoOptions):
        """Read `FinalDeck`s from `self.files` (async)."""

        async def finalize_deck_async(collection, deck):
            collection.append(await deck.finalize_async())

        final_decks = []
        async with asyncio.TaskGroup() as group:
            for deck in self.read(options):
                group.create_task(finalize_deck_async(final_decks, deck))

        return final_decks

    def read_final(self, options: VideoOptions):
        """Read `FinalDeck`s from `self.files`."""
        return asyncio.run(self.read_final_async(options))

    def read_final_sorted(self, options: VideoOptions):
        """Read `FinalDeck`s from `self.files` and sort by title."""
        return sorted(self.read_final(options), key=lambda deck: deck.title)


def deck_parameters(func):
    """Add a `decks` argument along with tag filtering options to a command.

    Adds the following options:
    - -i/--include-tag: Only include notes that have all specified tags
    - -x/--exclude-tag: Exclude notes that have any of the specified tags

    The decorated function must take a `decks` parameter of type `DeckSource`.
    """

    @click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
    @click.option(
        "-i",
        "--include-tag",
        multiple=True,
        default=[],
        metavar="TAG",
        help="Only include notes that have tag TAG. If specified multiple "
        "times, notes must have all TAGs.",
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
        # Create DeckSource from the tag options
        kwargs["decks"] = DeckSource(
            files=kwargs.pop("decks"),
            tags_include=frozenset(kwargs.pop("include_tag")),
            tags_exclude=frozenset(kwargs.pop("exclude_tag")),
        )

        return func(*args, **kwargs)

    return wrapper
