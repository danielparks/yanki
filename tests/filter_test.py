import io

from yanki.filter import DeckFilter, read_deck_specs

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


def parse_deck(filter):
    input = io.StringIO(REFERENCE_DECK)
    input.name = "-"

    return "".join(
        [
            spec.text()
            for deck in read_deck_specs([input], filter)
            for spec in deck.note_specs
        ]
    )


def test_filters():
    assert "ABCDEF" == parse_deck(DeckFilter())
    assert "ABC" == parse_deck(DeckFilter(include=["abc"]))
    assert "DEF" == parse_deck(DeckFilter(exclude=["abc"]))
    assert "" == parse_deck(DeckFilter(include=["abc"], exclude=["abc"]))
    assert "ABC" == parse_deck(DeckFilter(include=["abc"], exclude=["def"]))
    assert "A" == parse_deck(DeckFilter(include=["abc"], exclude=["bcd"]))


def test_multiple_include():
    assert "BC" == parse_deck(DeckFilter(include=["abc", "bcd"]))
    assert "C" == parse_deck(DeckFilter(include=["abc", "bcd"], exclude=["b"]))


def test_multiple_exclude():
    assert "EF" == parse_deck(DeckFilter(exclude=["abc", "bcd"]))
    assert "E" == parse_deck(DeckFilter(include=["e"], exclude=["abc", "bcd"]))
