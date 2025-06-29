import io
import logging
import textwrap

import pytest

from yanki.errors import DeckSyntaxError
from yanki.parser import DeckFilesParser
from yanki.utils import add_trace_logging

add_trace_logging()
logging.getLogger("yanki.parser").setLevel(logging.TRACE)


def parse_maybe_deck(contents, name="-"):
    return list(DeckFilesParser().parse_file(name, io.StringIO(contents)))


def parse_deck(contents, name="-"):
    specs = parse_maybe_deck(contents, name=name)
    assert len(specs) == 1
    return specs[0]


def parse_deck_dedent(contents, name="-"):
    # Strip extra indents.
    return parse_deck(textwrap.dedent(contents), name=name)


def test_empty_deck():
    assert len(parse_maybe_deck("")) == 0


def test_group():
    deck = parse_deck_dedent(
        """
        title: a
        version: 1
        overlay_text: deck
        file:///one outer1
        group:
            overlay_text: group1
            file:///two group1a
            file:///three group1b

            overlay_text: group1b
            file:///four group1c

            group:
                overlay_text: + group2
                file:///five group2a
        file:///six outer2
        """
    )
    assert deck.config.overlay_text == "deck"
    assert len(deck.note_specs) == 6

    assert deck.note_specs[0].video_url() == "file:///one"
    assert deck.note_specs[0].text() == "outer1"
    assert deck.note_specs[0].config.overlay_text == "deck"

    assert deck.note_specs[1].video_url() == "file:///two"
    assert deck.note_specs[1].text() == "group1a"
    assert deck.note_specs[1].config.overlay_text == "group1"

    assert deck.note_specs[2].video_url() == "file:///three"
    assert deck.note_specs[2].text() == "group1b"
    assert deck.note_specs[2].config.overlay_text == "group1"

    assert deck.note_specs[3].video_url() == "file:///four"
    assert deck.note_specs[3].text() == "group1c"
    assert deck.note_specs[3].config.overlay_text == "group1b"

    assert deck.note_specs[4].video_url() == "file:///five"
    assert deck.note_specs[4].text() == "group2a"
    assert deck.note_specs[4].config.overlay_text == "group1b group2"

    assert deck.note_specs[5].video_url() == "file:///six"
    assert deck.note_specs[5].text() == "outer2"
    assert deck.note_specs[5].config.overlay_text == "deck"


@pytest.mark.parametrize(
    ("lines", "more_html"),
    [
        (["more: one"], "one"),
        (["more: one", "more: two"], "two"),
        (["more: one", "more: +two"], "onetwo"),
        (["more: one", "  two"], "one<br/>two"),
        (["more: html:one", "  two"], "one\ntwo"),
        (["more: html:one", "", "  two"], "one\n\ntwo"),
        (["more: html:one", "  more: two"], "one\nmore: two"),
    ],
)
def test_deck_more_parametrized(lines, more_html):
    deck = parse_deck("title: a\n" + "\n".join(lines))
    assert len(deck.note_specs) == 0
    assert deck.config.more.render_html() == more_html


@pytest.mark.parametrize(
    ("lines", "overlay_text"),
    [
        (["overlay_text: one"], "one"),
        (["overlay_text: one", ""], "one"),
        (["overlay_text: one", "overlay_text: two"], "two"),
        (["overlay_text: one", "overlay_text: +two"], "onetwo"),
        (["overlay_text: one", "overlay_text:"], ""),
        (["overlay_text: one", "overlay_text:     \t"], ""),
        (["overlay_text: one", "overlay_text:     \t", ""], ""),
    ],
)
def test_deck_overlay_text_parametrized(lines, overlay_text):
    deck = parse_deck("title: a\n" + "\n".join(lines))
    assert len(deck.note_specs) == 0
    assert deck.config.overlay_text == overlay_text


@pytest.mark.parametrize(
    ("lines", "overlay_text"),
    [
        (["  overlay_text:"], ""),
        (["  overlay_text:", ""], ""),
        (["  overlay_text:     \t"], ""),
        (["  overlay_text:     \t", ""], ""),
        (["  overlay_text: one"], "one"),
        (["  overlay_text: one", ""], "one"),
        (["  overlay_text: one", "    two"], "one\ntwo"),
        (["  overlay_text: one", "", "    two"], "one\n\ntwo"),
        (["  overlay_text: one", "", "      two"], "one\n\ntwo"),
        (["  overlay_text: one", "", "    two", ""], "one\n\ntwo"),
        (["  overlay_text: one", "", "    two", "    "], "one\n\ntwo"),
        (["  overlay_text: one", "", "    two", "      "], "one\n\ntwo"),
        (
            ["  overlay_text: one", "", "    two", "      three"],
            "one\n\ntwo\n  three",
        ),
        (
            ["  overlay_text: one", "", "    two", "      ", "    three"],
            "one\n\ntwo\n\nthree",
        ),
        (["  overlay_text: one", "  overlay_text: two"], "two"),
        (["  overlay_text: one", "  overlay_text: +two"], "onetwo"),
        (["  overlay_text: one", "  overlay_text:"], ""),
        (["  overlay_text: one", "  overlay_text:", ""], ""),
        (["  overlay_text: one", "  overlay_text:     \t"], ""),
        (["  overlay_text: one", "  overlay_text:     \t", ""], ""),
        # Test quotes
        (["  overlay_text: one", '    "two"'], 'one\n"two"'),
    ],
)
def test_note_overlay_text_parametrized(lines, overlay_text):
    deck = parse_deck(
        "title: a\noverlay_text: deck\nfile:///foo note\n"
        + "\n".join(lines)
        + "\n\nfile:///bar note2\n"
    )
    assert len(deck.note_specs) == 2
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].text() == "note"
    assert deck.note_specs[0].config.overlay_text == overlay_text
    assert deck.note_specs[1].text() == "note2"
    assert deck.note_specs[1].config.overlay_text == "deck"


@pytest.mark.parametrize(
    ("note_lines", "parsed_text"),
    [
        (["one", "  two", "  \t", "  three"], "one\ntwo\n\nthree"),
        (["one", "  two", "  ", "  three"], "one\ntwo\n\nthree"),
        (["one", "  two", " ", "  three"], "one\ntwo\n\nthree"),
        (["one", "  two", "", "  three"], "one\ntwo\n\nthree"),
        (["one", "  two", "  \tthree"], "one\ntwo\n\tthree"),
        (["one  ", ""], "one"),
        (["one  ", "  two  ", "     "], "one  \ntwo"),
        (
            ["one", "  overlay_text: ignore", "  two", "", "  three"],
            "one\ntwo\n\nthree",
        ),
        (
            ["one", "  two", "   overlay_text: not config", "  four"],
            "one\ntwo\n overlay_text: not config\nfour",
        ),
        (
            ["one", "  #two", "  three"],
            "one\n#two\nthree",
        ),
        (
            ["overlay_text: not config", "  two"],
            "overlay_text: not config\ntwo",
        ),
        (
            ["#one", "  two"],
            "#one\ntwo",
        ),
        # Test quotes
        (
            ["quotes", '  "crop: 1:1"', '  " "', "  last"],
            "quotes\ncrop: 1:1\n \nlast",
        ),
        (
            ["quotes", '  "crop: 1:1"', '  ""', "  last"],
            "quotes\ncrop: 1:1\n\nlast",
        ),
        (["quotes", '  "crop: 1:1  "', "  last"], "quotes\ncrop: 1:1  \nlast"),
        (
            ["quotes", '  "crop: 1:1"  ', "  last"],
            'quotes\n"crop: 1:1"  \nlast',
        ),
        (["quotes", '  "crop: 1:1  "'], "quotes\ncrop: 1:1"),
        (["quotes", '  "crop: 1:1"  '], 'quotes\n"crop: 1:1"'),
    ],
)
def test_note_parametrized(note_lines, parsed_text):
    deck = parse_deck(
        "title: a\nfile:///foo "
        + "\n".join(note_lines)
        + "\nfile:///bar note2\n"
    )
    assert len(deck.note_specs) == 2
    assert deck.note_specs[0].text() == parsed_text
    assert deck.note_specs[1].text() == "note2"


@pytest.mark.parametrize(
    ("deck", "message"),
    [
        ("  bad", "Error in -, line 1: Unexpected indent"),
        (
            "title: a\nfile:///foo one\n  two\n bad",
            "Error in -, line 4: Unexpected indent",
        ),
        (
            "title: a\nfile:///foo note\n  illegal2: one",
            "Error in -, line 3: Invalid config directive 'illegal2'",
        ),
        (
            "file:///foo one",
            "Error in -, line 0: Does not contain title",
        ),
        (
            "title: a\n\tmore title",
            "Error in -, line 1: Title cannot have more than one line",
        ),
        (
            "version: 2",
            "Error in -, line 1: This version of yanki only supports version 1 "
            "deck files (found '2')",
        ),
        (
            "version:",
            "Error in -, line 1: This version of yanki only supports version 1 "
            "deck files (found '')",
        ),
        (
            "title: a\ngroup:\n  title: one",
            "Error in -, line 3: Title cannot be set within group",
        ),
        (
            "title: a\ngroup:\n  version: 1",
            "Error in -, line 3: Version cannot be set within group",
        ),
        (
            "title: a\nfile:///foo note\n  title: one",
            "Error in -, line 3: Title cannot be set within note",
        ),
        (
            "title: a\nfile:///foo note\n  version: 1",
            "Error in -, line 3: Version cannot be set within note",
        ),
        (
            "title: a\nfile:///foo note\n  group:\n    foobar",
            "Error in -, line 3: Group cannot be started within note",
        ),
    ],
)
def test_errors_parametrized(deck, message):
    with pytest.raises(DeckSyntaxError) as error_info:
        parse_deck(deck)
    assert str(error_info.value) == message
