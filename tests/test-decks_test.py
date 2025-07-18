import logging
from pathlib import Path

import pytest

from yanki.cli.decks import DeckSource
from yanki.utils import find_errors
from yanki.video import VideoOptions

LOGGER = logging.getLogger(__name__)


def find_deck_files(base_path):
    yield from Path(base_path).rglob("*.deck")


def read_first_line(path: Path):
    with path.open("r", encoding="utf_8") as input:
        for line in input:
            return line
    return None


@pytest.mark.parametrize("path", find_deck_files("test-decks/errors"))
def test_deck_error(path):
    with (
        path.open("r", encoding="utf_8") as file,
        pytest.raises(ExceptionGroup) as error_info,
    ):
        DeckSource(files=[file]).read_final(VideoOptions())

    [error] = list(find_errors(error_info.value))
    LOGGER.info("Caught exception", exc_info=error)

    first_line = read_first_line(path)
    assert first_line[0:2] == "# "
    assert first_line[-1] == "\n"
    assert str(error) == first_line[2:-1]


@pytest.mark.parametrize("path", find_deck_files("test-decks/good"))
def test_deck_success(path):
    with path.open("r", encoding="utf_8") as file:
        [deck] = DeckSource(files=[file]).read_final(VideoOptions())
    assert len(deck.notes()) >= 1
