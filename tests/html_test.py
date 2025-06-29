import html
import re

from yanki.cli.decks import DeckSource
from yanki.html_out import write_html
from yanki.video import VideoOptions


def test_two_decks(cache_path, deck_1_path, deck_2_path, output_path):
    files = [
        path.open("r", encoding="utf_8") for path in [deck_1_path, deck_2_path]
    ]

    write_html(
        output_path,
        cache_path,
        DeckSource(files=files).read_final_sorted(VideoOptions(cache_path)),
        flashcards=False,
    )

    index_html = (output_path / "index.html").read_text(encoding="utf_8")
    assert index_html.startswith("<!DOCTYPE html>\n")
    assert index_html.endswith("</html>\n")

    matches = re.findall(r'<a href="(deck_[^"]+)"', index_html)
    assert len(matches) == 2

    deck_path = html.unescape(matches[0])
    deck_html = (output_path / deck_path).read_text(encoding="utf_8")
    assert deck_html.startswith("<!DOCTYPE html>\n")
    assert deck_html.endswith("</html>\n")
    assert deck_html.count('<div class="note">') == 1

    deck_path = html.unescape(matches[1])
    deck_html = (output_path / deck_path).read_text(encoding="utf_8")
    assert deck_html.startswith("<!DOCTYPE html>\n")
    assert deck_html.endswith("</html>\n")
    assert deck_html.count('<div class="note">') == 1
