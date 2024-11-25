import fileinput

from downloader.anki import DeckParser

def cli():
  DeckParser(debug=False).parse_input(fileinput.input(encoding="utf-8"))
