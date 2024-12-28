import genanki
import os
import pytest

from yanki.anki import Deck
from yanki.parser import DeckParser, SyntaxError
from yanki.video import BadURL

def all_error_decks():
  for (dir_path, _, file_names) in os.walk('test-decks/errors'):
    for file_name in file_names:
      yield f'{dir_path}/{file_name}'

def read_first_line(path):
  with open(path, 'r', encoding='UTF-8') as input:
    for line in input:
      return line

def parse_deck(path, tmp_path):
  cache_path = tmp_path/'cache'
  os.makedirs(cache_path, exist_ok=True)
  parser = DeckParser(cache_path=cache_path)

  decks = [Deck(spec) for spec in parser.parse_path(path)]
  assert len(decks) == 1
  return decks[0]

@pytest.mark.parametrize('path', all_error_decks())
def test_deck_error(path, tmp_path):
  assert path.endswith('.deck')

  first_line = read_first_line(path)
  assert first_line[0:2] == '# '
  expected_message = first_line[2:-1] # Strip newline

  package = genanki.Package([])
  with pytest.raises(Exception) as error_info:
    parse_deck(path, tmp_path).save_to_package(package)

  assert str(error_info.value) == expected_message
