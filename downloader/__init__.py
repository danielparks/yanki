import genanki
import hashlib
import fileinput
import html
import os
import sys

from video import Video

CACHE = './cache'
os.makedirs(CACHE, exist_ok=True)

def name_to_id(name):
  bytes = hashlib.sha256(name.encode('utf-8')).digest()
  # Apparently deck ID is i64
  return int.from_bytes(bytes[:8], byteorder='big', signed=True)

class Deck:
  def __init__(self, source=None):
    self.source = source
    self._deck = None
    self.title = None
    self.tags = []
    self.media = []

  def deck(self):
    if not self._deck:
      self._deck = genanki.Deck(name_to_id(self.title), self.title)
    return self._deck

  def add_video_note(self, question, video_path, note_id):
    self.media.append(video_path)
    question_html = html.escape(question).rstrip().replace("\n", "<br/>")
    media_filename_html = html.escape(os.path.basename(video_path))

    self.deck().add_note(genanki.Note(
      model=genanki.BASIC_AND_REVERSED_CARD_MODEL,
      fields=[
        question_html,
        f"[sound:{media_filename_html}]",
      ],
      guid=genanki.guid_for(self.deck().deck_id, note_id),
      tags=self.tags,
    ))

  def save(self, path=None):
    if not path:
      path = os.path.splitext(self.source)[0] + '.apkg'

    package = genanki.Package(self._deck)
    package.media_files = self.media
    package.write_to_file(path)

class DeckParser:
  def __init__(self):
    self.deck = None
    self.path = None
    self.note = []

  def open(self, path):
    if self.deck:
      self.close()
    self.deck = Deck(path)
    self.path = path
    self.note = []

  def close(self):
    if len(self.note) > 0:
      self._parse_note()
    if self.deck:
      self.deck.save()

    self.deck = None
    self.path = None
    self.note = []

  def parse_line(self, path, line_number, line):
    if not self.deck:
      self.open(path)

    if line.startswith("#"):
      return

    unindented = line.lstrip(" \t")
    if line != unindented:
      # Line is indented and thus a continuation of a note
      if len(self.note) == 0:
        # FIXME terrible error message
        raise ValueError(f"Found indented line with no preceding line ({self.path}, line {line_number})")

      self.note.append(unindented)
      return

    if line.strip() == "":
      # Blank lines only count inside notes.
      if len(self.note) > 0:
        self.note.append(line)
      return

    # Line is not indented
    if len(self.note) > 0:
      self._parse_note()
      self.note = []

    if line.startswith("title:"):
      self.deck.title = line.removeprefix("title:").strip()
    elif line.startswith("tags:"):
      self.deck.tags = line.removeprefix("tags:").split()
    else:
      self.note.append(line)

  def _parse_note(self):
    lines = "".join(self.note)
    note = lines.split(maxsplit=1)

    if len(note) == 0:
      # FIXME wrong exception
      raise ValueError("_parse_note() called on empty input")

    video = Video(note[0], cache_path=CACHE)
    if len(note) == 2:
      question = note[1]
    else:
      question = video.title()

    self.deck.add_video_note(
      question,
      video.processed_video(),
      f"youtube {video.id}")


if __name__ == '__main__':
  parser = DeckParser()
  for line in fileinput.input(encoding="utf-8"):
    parser.parse_line(fileinput.filename(), fileinput.filelineno(), line)
  parser.close()
