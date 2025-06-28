import os

import pytest

from yanki.cli.decks import DeckSource
from yanki.utils import find_errors
from yanki.video import VideoOptions


def find_deck_files(base_path):
    for dir_path, _, file_names in os.walk(base_path):
        for file_name in file_names:
            if file_name.endswith(".deck"):
                yield f"{dir_path}/{file_name}"


def read_first_line(path):
    with open(path, "r", encoding="utf_8") as input:
        for line in input:
            return line


@pytest.mark.parametrize("path", find_deck_files("test-decks/errors"))
def test_deck_error(path, cache_path):
    options = VideoOptions(cache_path=cache_path)
    with open(path, "r", encoding="utf_8") as file:
        with pytest.raises(Exception) as error_info:
            DeckSource(files=[file]).read_final(options)

    [error] = list(find_errors(error_info.value))

    first_line = read_first_line(path)
    assert first_line[0:2] == "# "
    assert first_line[-1] == "\n"
    assert str(error) == first_line[2:-1]


@pytest.mark.parametrize("path", find_deck_files("test-decks/good"))
def test_deck_success(path, cache_path):
    options = VideoOptions(cache_path=cache_path)
    with open(path, "r", encoding="utf_8") as file:
        [deck] = DeckSource(files=[file]).read_final(options)
    assert len(deck.notes()) >= 1
