import io

from yanki.cli.decks import DeckSource
from yanki.video import VideoOptions

REFERENCE_DECK = """
title: a
tags: +abc
file:///a A
tags: +bcd
file:///b B
    tags: +b
file:///c C
tags: -abc +def
file:///d D
tags: -bcd
file:///e E
    tags: +e
file:///f F
tags: -def
"""


def filter_deck_tags(include=set(), exclude=set()):
    input = io.StringIO(REFERENCE_DECK)
    input.name = "-"

    source = DeckSource(
        files=[input], tags_include=set(include), tags_exclude=set(exclude)
    )

    return "".join(
        [
            spec.text()
            for deck in source.read_specs()
            for spec in deck.note_specs
        ]
    )


def test_filters():
    assert "ABCDEF" == filter_deck_tags()
    assert "ABC" == filter_deck_tags(include=["abc"])
    assert "DEF" == filter_deck_tags(exclude=["abc"])
    assert "" == filter_deck_tags(include=["abc"], exclude=["abc"])
    assert "ABC" == filter_deck_tags(include=["abc"], exclude=["def"])
    assert "A" == filter_deck_tags(include=["abc"], exclude=["bcd"])


def test_multiple_include():
    assert "BC" == filter_deck_tags(include=["abc", "bcd"])
    assert "C" == filter_deck_tags(include=["abc", "bcd"], exclude=["b"])


def test_multiple_exclude():
    assert "EF" == filter_deck_tags(exclude=["abc", "bcd"])
    assert "E" == filter_deck_tags(include=["e"], exclude=["abc", "bcd"])


def test_read_decks_sorted(deck_1_path, deck_2_path, cache_path):
    decks = DeckSource(
        files=[
            open(deck_2_path, "r", encoding="utf_8"),
            open(deck_1_path, "r", encoding="utf_8"),
        ]
    ).read_sorted(VideoOptions(cache_path))

    assert len(decks) == 2
    assert decks[0].title() == "Test::Reference deck"
    assert decks[1].title() == "Test::Reference deck::2"


def test_read_final_decks_sorted(deck_1_path, deck_2_path, cache_path):
    decks = DeckSource(
        files=[
            open(deck_2_path, "r", encoding="utf_8"),
            open(deck_1_path, "r", encoding="utf_8"),
        ]
    ).read_final_sorted(VideoOptions(cache_path))

    assert len(decks) == 2
    assert decks[0].title == "Test::Reference deck"
    assert decks[1].title == "Test::Reference deck::2"
