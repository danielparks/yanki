import genanki
import hashlib
import fileinput
import html
import os
import sys

from video import Video

CACHE = './cache'
os.makedirs(CACHE, exist_ok=True)

DEBUG = False

def name_to_id(name):
  bytes = hashlib.sha256(name.encode('utf-8')).digest()
  # Apparently deck ID is i64
  return int.from_bytes(bytes[:8], byteorder='big', signed=True)

class Deck:
  def __init__(self, source=None):
    self.source = source
    self._deck = None
    self.title = None
    self.crop = None
    self.tags = []
    self.media = []

  def deck(self):
    if not self._deck:
      self._deck = genanki.Deck(name_to_id(self.title), self.title)
      if DEBUG:
        print(f"New deck [{self._deck.deck_id}]: {self.title}")
    return self._deck

  def to_html(self, input):
    return html.escape(input).rstrip().replace("\n", "<br/>")

  def add_html_note(self, note_id, fields):
    self.deck().add_note(genanki.Note(
      model=genanki.BASIC_AND_REVERSED_CARD_MODEL,
      fields=fields,
      guid=genanki.guid_for(self.deck().deck_id, note_id),
      tags=self.tags,
    ))
    if DEBUG:
      print(f"Added note {note_id}: {fields}")

  def add_image_note(self, note_id, question, media_path):
    self.media.append(media_path)

    media_filename_html = html.escape(os.path.basename(media_path))
    self.add_html_note(note_id, [
      self.to_html(question),
      f"<img src=\"{media_filename_html}\"/>",
    ])

  def add_video_note(self, note_id, question, media_path):
    self.media.append(media_path)

    media_filename_html = html.escape(os.path.basename(media_path))
    self.add_html_note(note_id, [
      self.to_html(question),
      f"[sound:{media_filename_html}]",
    ])

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
    self.line_number = None
    self.note = []

  def open(self, path):
    if self.deck:
      self.close()
    self.deck = Deck(path)
    self.path = path
    self.line_number = None
    self.note = []

  def close(self):
    if len(self.note) > 0:
      self._parse_note()
    if self.deck:
      self.deck.save()

    self.deck = None
    self.path = None
    self.line_number = None
    self.note = []

  def where(self):
    return f"{self.path}, line {self.line_number}"

  def parse_line(self, path, line_number, line):
    if not self.deck or self.path != path:
      self.open(path)

    self.line_number = line_number

    if line.startswith("#"):
      return

    unindented = line.lstrip(" \t")
    if line != unindented:
      # Line is indented and thus a continuation of a note
      if len(self.note) == 0:
        # FIXME terrible error message
        raise ValueError(f"Found indented line with no preceding line ({self.where()})")

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
    elif line.startswith("crop:"):
      self.deck.crop = line.removeprefix("crop:").strip()
    else:
      self.note.append(line)

  def _parse_note(self):
    note = "".join(self.note).split(maxsplit=1)

    if len(note) == 0:
      # FIXME wrong exception
      raise ValueError("_parse_note() called on empty input ({self.where()})")

    video = Video(note[0], cache_path=CACHE)
    if self.deck.crop:
      video.crop(self.deck.crop)

    if len(note) == 2:
      question = self._try_parse_clip(note[1], video)
    else:
      question = video.title()

    output_id = " ".join(video.output_id)
    answer = video.processed_video()
    if video.output_ext == "jpeg":
      self.deck.add_image_note(f"youtube {output_id}", question, answer)
    else:
      self.deck.add_video_note(f"youtube {output_id}", question, answer)

  def _try_parse_clip(self, input, video):
    if not input.startswith("@"):
      return input

    parts = input.split(maxsplit=1)

    if len(parts) >= 1:
      clip = parts[0].removeprefix("@").split("-")
      if len(clip) == 2:
        video.clip(clip[0], clip[1])
      elif len(clip) == 1:
        video.snapshot(clip[0])
      else:
        raise ValueError(f"Invalid clip specification {repr(parts[0])} ({self.where()})")

    # Return rest of input
    if len(parts) == 2:
      return parts[1]
    else:
      return ""


if __name__ == '__main__':
  parser = DeckParser()
  for line in fileinput.input(encoding="utf-8"):
    parser.parse_line(fileinput.filename(), fileinput.filelineno(), line)
  parser.close()
