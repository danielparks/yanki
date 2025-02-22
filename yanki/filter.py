import click
import asyncio

from yanki.parser import DeckFilesParser
from yanki.anki import Deck
from yanki.video import VideoOptions
from yanki.parser import NoteSpec, DeckSpec


class DeckFilter:
    """Filter notes in decks."""

    def __init__(self, include=set(), exclude=set()):
        self.tags_include = set(include)
        self.tags_exclude = set(exclude)

    def _include_note(self, note_spec: NoteSpec):
        tags = note_spec.config.tags
        # fmt: off
        return (
            self.tags_include.issubset(tags)
            and self.tags_exclude.isdisjoint(tags)
        )

    def filter(self, deck_spec: DeckSpec):
        filtered = []
        for note_spec in deck_spec.note_specs:
            if self._include_note(note_spec):
                filtered.append(note_spec)
        if filtered:
            deck_spec.note_specs = filtered
            yield deck_spec


def _filter_callback(ctx, param, value):
    """Convert options into `DeckFilter`."""
    if "filter" not in ctx.params:
        ctx.params["filter"] = DeckFilter()

    if param.name == "exclude_tag":
        ctx.params["filter"].tags_exclude = set(value)
    elif param.name == "include_tag":
        ctx.params["filter"].tags_include = set(value)
    else:
        raise ValueError(f"Unknown parameter {param.name!r}")


def filter_options(function):
    """
    Add filter options to command.

    The option values will be converted into a `DeckFilter` object and passed
    as a `filter` keyword argument..
    """
    exclude = click.option(
        "-x",
        "--exclude-tag",
        default=[],
        metavar="TAG",
        multiple=True,
        show_default=True,
        help="Exclude notes that have tag TAG. If specified multiple times, "
        "notes with any tag in TAGs will be excluded.",
        callback=_filter_callback,
        expose_value=False,
    )
    include = click.option(
        "-i",
        "--include-tag",
        default=[],
        metavar="TAG",
        multiple=True,
        show_default=True,
        help="Only include notes that have tag TAG. If specified multiple "
        "times, notes must have all TAGs.",
        callback=_filter_callback,
        expose_value=False,
    )
    return exclude(include(function))


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


async def read_final_decks_async(
    files, options: VideoOptions, filter=DeckFilter()
):
    """Read `FinalDeck`s from `files` (async)."""

    async def finalize_deck(collection, deck):
        collection.append(await deck.finalize())

    final_decks = []
    async with asyncio.TaskGroup() as group:
        for deck in read_decks(files, options, filter):
            group.create_task(finalize_deck(final_decks, deck))

    return final_decks


def read_final_decks(files, options: VideoOptions, filter=DeckFilter()):
    """Read `FinalDeck`s from `files`."""
    return asyncio.run(read_final_decks_async(files, options, filter))
