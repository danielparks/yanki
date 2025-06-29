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


def filter_deck_tags(include=frozenset(), exclude=frozenset()):
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
    assert filter_deck_tags() == "ABCDEF"
    assert filter_deck_tags(include=["abc"]) == "ABC"
    assert filter_deck_tags(exclude=["abc"]) == "DEF"
    assert filter_deck_tags(include=["abc"], exclude=["abc"]) == ""
    assert filter_deck_tags(include=["abc"], exclude=["def"]) == "ABC"
    assert filter_deck_tags(include=["abc"], exclude=["bcd"]) == "A"


def test_multiple_include():
    assert filter_deck_tags(include=["abc", "bcd"]) == "BC"
    assert filter_deck_tags(include=["abc", "bcd"], exclude=["b"]) == "C"


def test_multiple_exclude():
    assert filter_deck_tags(exclude=["abc", "bcd"]) == "EF"
    assert filter_deck_tags(include=["e"], exclude=["abc", "bcd"]) == "E"


def test_read_decks_sorted(deck_1_path, deck_2_path, cache_path):
    decks = DeckSource(
        files=[
            deck_2_path.open("r", encoding="utf_8"),
            deck_1_path.open("r", encoding="utf_8"),
        ]
    ).read_sorted(VideoOptions(cache_path))

    assert len(decks) == 2
    assert decks[0].title() == "Test::Reference deck"
    assert decks[1].title() == "Test::Reference deck::2"


def test_read_final_decks_sorted(deck_1_path, deck_2_path, cache_path):
    decks = DeckSource(
        files=[
            deck_2_path.open("r", encoding="utf_8"),
            deck_1_path.open("r", encoding="utf_8"),
        ]
    ).read_final_sorted(VideoOptions(cache_path))

    assert len(decks) == 2
    assert decks[0].title == "Test::Reference deck"
    assert decks[1].title == "Test::Reference deck::2"
