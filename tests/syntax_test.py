import io
import pytest
import textwrap

from yanki.parser import DeckParser, DeckSyntaxError


def parse_deck(contents, name="-"):
    # Strip extra indents and pretend it’s a file.
    contents = io.StringIO(textwrap.dedent(contents))
    specs = list(DeckParser().parse_file(name, contents))
    assert len(specs) == 1
    return specs[0]


def test_two_mores():
    assert (
        parse_deck(
            """
                title: a
                more: one
                more: +two
            """
        ).config.more.render_html()
        == "onetwo"
    )


def test_overlays():
    assert (
        parse_deck(
            """
                title: a
                overlay_text: one
            """
        ).config.overlay_text
        == "one"
    )

    assert (
        parse_deck(
            """
                title: a
                overlay_text: one
                overlay_text: +two
            """
        ).config.overlay_text
        == "onetwo"
    )


def test_deck_config_whitespace():
    assert (
        parse_deck(
            """
                title: a
                overlay_text: one"""
        ).config.overlay_text
        == "one"
    )

    assert (
        parse_deck(
            """
                title: a
                overlay_text: one
                overlay_text:"""
        ).config.overlay_text
        == ""
    )

    assert (
        parse_deck(
            """
                title: a
                overlay_text: one
                overlay_text:     \t"""
        ).config.overlay_text
        == ""
    )

    assert (
        parse_deck(
            """
                title: a
                overlay_text: one
                overlay_text:
            """
        ).config.overlay_text
        == ""
    )


def test_note_config_whitespace():
    deck = parse_deck(
        """
            title: a
            overlay_text: deck

            file:///foo note
                overlay_text: one
        """
    )
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].config.overlay_text == "one"

    deck = parse_deck(
        """
            title: a
            overlay_text: deck

            file:///foo note
                overlay_text: one"""
    )
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].config.overlay_text == "one"

    deck = parse_deck(
        """
            title: a
            overlay_text: deck

            file:///foo note
                overlay_text:"""
    )
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].config.overlay_text == ""

    deck = parse_deck(
        """
            title: a
            overlay_text: deck

            file:///foo note
                overlay_text:     \t"""
    )
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].config.overlay_text == ""

    deck = parse_deck(
        """
            title: a
            overlay_text: deck

            file:///foo note
                overlay_text:
        """
    )
    assert deck.config.overlay_text == "deck"
    assert deck.note_specs[0].config.overlay_text == ""


def test_bad_config():
    with pytest.raises(DeckSyntaxError) as error_info:
        parse_deck(
            """
                title: a
                illegal: deck

                file:///foo note
                    overlay_text: one
            """
        )
    assert error_info.match("Invalid config directive 'illegal'")

    with pytest.raises(DeckSyntaxError) as error_info:
        parse_deck(
            """
                title: a

                file:///foo note
                    illegal2: one
            """
        )
    assert error_info.match("Invalid config directive 'illegal2'")


def test_multiline_more():
    with pytest.raises(DeckSyntaxError) as error_info:
        assert (
            parse_deck(
                """
                    title: a
                    more: html:one
                      two
                """
            ).config.more.render_html()
            == "one\ntwo"
        )
    assert error_info.match("Found indented line ")


def test_multiline_more_with_config():
    with pytest.raises(DeckSyntaxError) as error_info:
        assert (
            parse_deck(
                """
                    title: a
                    more: html:one
                      more: two
                """
            ).config.more.render_html()
            == "one\nmore: two"
        )
    assert error_info.match("Found indented line ")
