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
    media_filename_html = html.escape(os.path.basename(video_path))

    self.deck().add_note(genanki.Note(
      model=genanki.BASIC_AND_REVERSED_CARD_MODEL,
      fields=[
        html.escape(question),
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

if __name__ == '__main__':
  deck = None
  for line in fileinput.input(encoding="utf-8"):
    if fileinput.isfirstline():
      if deck:
        deck.save()
      deck = Deck(fileinput.filename())

    stripped = line.strip()
    if stripped == "" or stripped.startswith("#"):
      continue

    if stripped.startswith("title:"):
      deck.title = stripped.removeprefix("title:").strip()
    elif stripped.startswith("tags:"):
      deck.tags = stripped.removeprefix("tags:").split()
    else:
      video = Video(stripped, cache_path=CACHE)
      deck.add_video_note(
        video.title(),
        video.processed_video(),
        f"youtube {video.id}")

  if deck:
    deck.save()
