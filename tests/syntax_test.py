import io
import textwrap

from yanki.parser import DeckParser


def parse_deck(contents, name="-"):
    specs = list(DeckParser().parse_file(name, io.StringIO(contents)))
    assert len(specs) == 1
    return specs[0]


def test_two_mores():
    assert (
        parse_deck(
            textwrap.dedent("""
                title: a
                more: one
                more+ two
            """)
        ).scope.more.render_html()
        == "onetwo"
    )
