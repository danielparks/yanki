import genanki
import hashlib
import fileinput
import html
import os

from video import Video

CACHE = './cache'
os.makedirs(CACHE, exist_ok=True)

def name_to_id(name):
  bytes = hashlib.sha256(name.encode('utf-8')).digest()
  # Apparently deck ID is i64
  return int.from_bytes(bytes[:8], byteorder='big', signed=True)

def new_deck(name):
  return genanki.Deck(name_to_id(name), name)

if __name__ == '__main__':
  deck = new_deck('Lifeprint ASL (custom)::Lesson 1 phrases')
  tags = ['lesson_01', 'phrases']

  media = []
  for line in fileinput.input(encoding="utf-8"):
    if line.strip() == "" or line.strip().startswith("#"):
      continue

    video = Video(line, cache_path=CACHE)
    video_path = video.processed_video()
    media.append(video_path)

    basename_html = html.escape(os.path.basename(video_path))
    deck.add_note(genanki.Note(
      model=genanki.BASIC_AND_REVERSED_CARD_MODEL,
      fields=[
        html.escape(video.title()),
        f"[sound:{basename_html}]",
      ],
      guid=genanki.guid_for(video.id),
      tags=tags,
    ))

  package = genanki.Package(deck)
  package.media_files = media
  package.write_to_file('output.apkg')
