import os
import pytest


def find_deck_files(base_path):
    for dir_path, _, file_names in os.walk(base_path):
        for file_name in file_names:
            if file_name.endswith(".deck"):
                yield f"{dir_path}/{file_name}"


def read_first_line(path):
    with open(path, "r", encoding="UTF-8") as input:
        for line in input:
            return line


@pytest.mark.parametrize("path", find_deck_files("test-decks/errors"))
def test_deck_error(path, yanki):
    first_line = read_first_line(path)
    if first_line.startswith("#ends: "):
        expected_message = first_line.removeprefix("#ends: ")
    else:
        assert first_line[0:2] == "# "
        expected_message = first_line[2:]

    result = yanki.run("to-html", path)
    assert result.returncode == 1
    assert result.stdout == ""

    if first_line.startswith("#ends: "):
        assert result.stderr.endswith(expected_message)
    else:
        assert result.stderr == expected_message


@pytest.mark.parametrize("path", find_deck_files("test-decks/good"))
def test_deck_success(path, yanki):
    result = yanki.run("to-html", path)
    assert result.returncode == 0
    assert result.stderr == ""

    assert result.stdout.startswith("<!DOCTYPE html>\n")
    assert result.stdout.endswith("</html>\n")
    assert result.stdout.count('<div class="note">') >= 1
