import argparse
import fileinput

from yanki.anki import DeckParser

def cli():
  parser = argparse.ArgumentParser(
    prog='yanki',
    description='Builds an Anki deck from a text file containing YouTube URLs.',
  )
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('path', nargs='*')
  args = parser.parse_args()

  input = fileinput.input(files=args.path, encoding="utf-8")
  DeckParser(debug=args.verbose).parse_input(input)

  return 0
