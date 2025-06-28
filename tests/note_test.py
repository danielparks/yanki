import asyncio

from yanki.anki import FINAL_NOTE_VARIABLES, Note
from yanki.parser import NoteSpec
from yanki.parser.config import NOTE_VARIABLES, NoteConfig
from yanki.video import VideoOptions


def example_note_spec():
    return NoteSpec(
        source_path="-",
        line_number=1,
        source="file://test-decks/good/media/first.png text",
        config=NoteConfig().frozen(),
    )


def example_note(cache_path):
    return Note(example_note_spec(), VideoOptions(cache_path))


def test_note_spec_variables():
    assert set(example_note_spec().variables().keys()) == NOTE_VARIABLES


def test_note_variables(cache_path):
    assert set(example_note(cache_path).variables().keys()) == NOTE_VARIABLES


def test_final_note_variables(cache_path):
    note = asyncio.run(example_note(cache_path).finalize_async(deck_id=1))
    assert set(note.variables().keys()) == FINAL_NOTE_VARIABLES
