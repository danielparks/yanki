import genanki
import os
import pytest

from yanki.cli import read_final_decks, GlobalOptions


@pytest.fixture(scope="session")
def cache_path(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


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
    options = GlobalOptions(cache_path=cache_path)
    with open(path, "r", encoding="UTF-8") as file:
        decks = read_final_decks([file], options)
        assert len(decks) == 1
        return decks[0]


@pytest.mark.parametrize("path", find_deck_files("test-decks/errors"))
def test_deck_error(path, cache_path):
    first_line = read_first_line(path)
    assert first_line[0:2] == "# "
    expected_message = first_line[2:-1]  # Strip newline

    package = genanki.Package([])
    with pytest.raises(ExceptionGroup) as error_info:
        parse_deck(path, cache_path).save_to_package(package)

    exception = error_info.value.exceptions[0]
    while isinstance(exception, ExceptionGroup):
        exception = exception.exceptions[0]
    assert str(exception) == expected_message


@pytest.mark.parametrize("path", find_deck_files("test-decks/good"))
def test_deck_success(path, cache_path):
    package = genanki.Package([])
    deck = parse_deck(path, cache_path)
    assert len(deck.notes()) > 0
    deck.save_to_package(package)
