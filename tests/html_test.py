import html
import pytest
import re
import shutil

from yanki.filter import (
    DeckFilter,
    read_final_decks_sorted,
)
from yanki.html_out import write_html
from yanki.video import VideoOptions


REFERENCE_DECK_1 = """
title: Test::Reference deck
file://first.png text
"""
REFERENCE_DECK_2 = """
title: Test::Reference deck::2
file://second.png second text
"""


@pytest.fixture(scope="session")
def video_options(tmp_path_factory):
    return VideoOptions(tmp_path_factory.mktemp("cache"))


@pytest.fixture(scope="session")
def decks_path(tmp_path_factory):
    return tmp_path_factory.mktemp("decks")


@pytest.fixture(scope="session")
def deck_1_path(decks_path):
    shutil.copy("test-decks/good/media/first.png", decks_path / "first.png")
    path = decks_path / "reference_1.deck"
    path.write_text(REFERENCE_DECK_1, encoding="utf_8")
    return path


@pytest.fixture(scope="session")
def deck_2_path(decks_path):
    shutil.copy("test-decks/good/media/second.png", decks_path / "second.png")
    path = decks_path / "reference_2.deck"
    path.write_text(REFERENCE_DECK_2, encoding="utf_8")
    return path


def test_two_decks(video_options, deck_1_path, deck_2_path, tmp_path_factory):
    decks = [deck_1_path, deck_2_path]
    decks = [open(path, "r", encoding="utf_8") for path in decks]

    output_path = tmp_path_factory.mktemp("output")
    write_html(
        output_path,
        video_options.cache_path,
        read_final_decks_sorted(decks, video_options, DeckFilter()),
        flash_cards=False,
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
