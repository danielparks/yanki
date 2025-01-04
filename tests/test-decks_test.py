import genanki
import os
import pytest

from yanki.anki import Deck
from yanki.parser import DeckParser


def find_deck_files(base_path):
    for dir_path, _, file_names in os.walk(base_path):
        for file_name in file_names:
            if file_name.endswith(".deck"):
                yield f"{dir_path}/{file_name}"


def read_first_line(path):
    with open(path, "r", encoding="UTF-8") as input:
        for line in input:
            return line


def parse_deck(path, cache_path):
    decks = [
        Deck(spec, cache_path=cache_path)
        for spec in DeckParser().parse_path(path)
    ]
    assert len(decks) == 1
    return decks[0]


@pytest.mark.parametrize("path", find_deck_files("test-decks/errors"))
def test_deck_error(path, cache_path):
    first_line = read_first_line(path)
    assert first_line[0:2] == "# "
    expected_message = first_line[2:-1]  # Strip newline

    package = genanki.Package([])
    with pytest.raises(Exception) as error_info:
        parse_deck(path, cache_path).save_to_package(package)

    assert str(error_info.value) == expected_message


@pytest.mark.parametrize("path", find_deck_files("test-decks/good"))
def test_deck_success(path, cache_path):
    package = genanki.Package([])
    deck = parse_deck(path, cache_path)
    assert len(deck.notes) > 0
    deck.save_to_package(package)
