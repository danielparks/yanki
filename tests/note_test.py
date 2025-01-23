import asyncio
from yanki.parser.config import NoteConfig, NOTE_VARIABLES
from yanki.parser import NoteSpec
from yanki.anki import Note, FINAL_NOTE_VARIABLES
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
    note = asyncio.run(example_note(cache_path).finalize(deck_id=1))
    assert set(note.variables().keys()) == FINAL_NOTE_VARIABLES
