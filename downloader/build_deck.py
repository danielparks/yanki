import fileinput

from downloader.anki import DeckParser

def cli():
  parser = DeckParser()
  for line in fileinput.input(encoding="utf-8"):
    parser.parse_line(fileinput.filename(), fileinput.filelineno(), line)
  parser.close()
