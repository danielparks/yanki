import html
import re
import shutil
from pathlib import Path

from yanki.cli.decks import DeckSource
from yanki.video import VideoOptions
from yanki.web.summary import write_html


def deck_paths_to_html(output_path: Path, deck_paths: list[Path]):
    options = VideoOptions()
    files = [path.open("r") for path in deck_paths]

    write_html(output_path, DeckSource(files=files).read_final_sorted(options))


def read_html(path):
    content = path.read_text()
    assert content.startswith("<!DOCTYPE html>\n")
    assert content.endswith("</html>\n")
    return content


def assert_count(content: str, needle: str, count: int):
    assert content.count(needle) == count, (
        f"expect exactly {count} {needle!r} in HTML"
    )


def assert_notes(content: str, note_count: int):
    assert_count(content, '<div class="note">', note_count)


def test_one_deck(deck_1_path, output_path):
    deck_paths_to_html(output_path, [deck_1_path])

    # index.html should be a deck, not an index.
    index_html = read_html(output_path / "index.html")
    assert_notes(index_html, 1)
    assert re.findall(r'<a href="(deck_[^"]+)"', index_html) == []


def test_overwrite_deck(deck_1_path, deck_2_path, output_path):
    deck_paths_to_html(output_path, [deck_1_path])

    # index.html should be a deck, not an index.
    index_html = read_html(output_path / "index.html")
    assert_notes(index_html, 1)
    assert_count(index_html, "_file%5C%3D%7C%7Cfirst.png_", 1)
    assert_count(index_html, "_file%5C%3D%7C%7Csecond.png_", 0)
    assert re.findall(r'<a href="(deck_[^"]+)"', index_html) == []

    deck_paths_to_html(output_path, [deck_2_path])

    # index.html should be a deck, not an index.
    index_html = read_html(output_path / "index.html")
    assert_notes(index_html, 1)
    assert_count(index_html, "_file%5C%3D%7C%7Cfirst.png_", 0)
    assert_count(index_html, "_file%5C%3D%7C%7Csecond.png_", 1)
    assert re.findall(r'<a href="(deck_[^"]+)"', index_html) == []


def test_two_decks(deck_1_path, deck_2_path, output_path):
    deck_paths_to_html(output_path, [deck_1_path, deck_2_path])

    index_html = read_html(output_path / "index.html")
    matches = re.findall(r'<a href="(deck_[^"]+)"', index_html)
    assert len(matches) == 2

    deck_html = read_html(output_path / html.unescape(matches[0]))
    assert_notes(deck_html, 1)
    assert_count(deck_html, "_file%5C%3D%7C%7Cfirst.png_", 1)
    assert_count(deck_html, "_file%5C%3D%7C%7Csecond.png_", 0)

    deck_html = read_html(output_path / html.unescape(matches[1]))
    assert_notes(deck_html, 1)
    assert_count(deck_html, "_file%5C%3D%7C%7Cfirst.png_", 0)
    assert_count(deck_html, "_file%5C%3D%7C%7Csecond.png_", 1)


def test_conflicting_deck_titles(output_path, decks_path):
    shutil.copy("test-decks/good/media/first.png", decks_path / "first.png")
    decks = [
        "title: Test::D/E C K\nfile://first.png text\n",
        "title: Test::D E/C K\nfile://first.png text\n",
        "title: Test::D E C/K\nfile://first.png text\n",
    ]
    deck_paths = [
        decks_path / f"conflict_{i + 1}.deck" for i in range(len(decks))
    ]
    for i, path in enumerate(deck_paths):
        path.write_text(decks[i])

    deck_paths_to_html(output_path, deck_paths)

    index_html = read_html(output_path / "index.html")
    names = [
        html.unescape(match)
        for match in re.findall(r'<a href="(deck_[^"]+)"', index_html)
    ]
    assert names == [
        "deck_Test_D_E_C_K.html",
        "deck_Test_D_E_C_K_2.html",
        "deck_Test_D_E_C_K_3.html",
    ]

    for name in names:
        content = read_html(output_path / name)
        assert_notes(content, 1)
