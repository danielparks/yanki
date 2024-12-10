import genanki
import hashlib
import html
import logging
import os
import sys

LOGGER = logging.getLogger(__name__)

from yanki.video import Video

REVERSED_CARD_MODEL = genanki.Model(
  1221938101,
  'Reversed (yanki)',
  fields=genanki.BASIC_MODEL.fields.copy(),
  templates=[
    {
      'name': 'Card 2',
      'qfmt': '{{Back}}',
      'afmt': '{{FrontSide}}\n\n<hr id=answer>\n\n{{Front}}',
    },
  ],
  css=genanki.BASIC_MODEL.css,
)

def name_to_id(name):
  bytes = hashlib.sha256(name.encode('utf-8')).digest()
  # Apparently deck ID is i64
  return int.from_bytes(bytes[:8], byteorder='big', signed=True)

class Field:
  def __init__(self, raw):
    self.raw = raw

  def media_paths(self):
    return []

  def render_anki(self):
    return self.render_html('')

  def render_html(self, base_path=''):
    return html.escape(self.raw).rstrip().replace("\n", "<br/>")

  def __str__(self):
    return self.render_anki()

  def __repr__(self):
    return repr(self.render_anki())

class MediaField(Field):
  def __init__(self, path):
    self.path = path

  def path_in_base(self, base_path):
    return os.path.join(base_path, os.path.basename(self.path))

  def media_paths(self):
    return [self.path]

class ImageField(MediaField):
  def render_html(self, base_path=''):
    media_filename_html = html.escape(self.path_in_base(base_path))
    return f'<img src="{media_filename_html}" />'

class VideoField(MediaField):
  def render_anki(self):
    media_filename_html = html.escape(self.path_in_base(''))
    return f"[sound:{media_filename_html}]"

  def render_html(self, base_path='.'):
    media_filename_html = html.escape(self.path_in_base(base_path))
    return f'<video controls src="{media_filename_html}"></video>'

class Note:
  def __init__(self, note_id, fields, tags, direction='<->'):
    self.note_id = note_id
    self.fields = fields
    self.tags = tags
    self.direction = direction

  def add_to_deck(self, deck):
    if self.direction == '<->':
      model = genanki.BASIC_AND_REVERSED_CARD_MODEL
    elif self.direction == '<-':
      model = genanki.BASIC_MODEL
    elif self.direction == '->':
      model = REVERSED_CARD_MODEL
    else:
      raise ValueError(f"Invalid direction {self.direction}")

    deck.add_note(genanki.Note(
      model=model,
      fields=[field.render_anki() for field in self.fields],
      guid=genanki.guid_for(deck.deck_id, self.note_id),
      tags=self.tags,
    ))

class Deck:
  def __init__(self, source=None):
    self.source = source
    self.title = None
    self.crop = None
    self.format = None
    self.notes = {}
    self.tags = []
    self.slow = None
    self.audio = 'include'
    self.video = 'include'

  def add_slow(self, slow_spec):
    if slow_spec.strip() == '':
      self.slow = None
      return

    parts = [p.strip() for p in slow_spec.split('*')]
    if len(parts) != 2:
      self.slow = None
      raise ValueError(f"Invalid slow without '*': {slow_spec}")

    amount = float(parts[1])

    parts = [p.strip() for p in parts[0].split('-')]
    if len(parts) != 2:
      self.slow = None
      raise ValueError(f"Invalid slow without '-': {slow_spec}")

    start = parts[0]
    if start == '':
      start = '0'

    end = parts[1]
    if end == '':
      end = None

    self.slow = (start, end, amount)

  def set_audio(self, audio):
    if audio == 'include' or audio == 'strip':
      self.audio = audio
    else:
      raise ValueError('audio must be either "include" or "strip"')

  def set_video(self, video):
    if video == 'include' or video == 'strip':
      self.video = video
    else:
      raise ValueError('video must be either "include" or "strip"')

  def add_note(self, note):
    if note.note_id in self.notes:
      raise LookupError(f"Note with id {note.note_id} already exists in deck")
    self.notes[note.note_id] = note

  def save_to_package(self, package):
    deck = genanki.Deck(name_to_id(self.title), self.title)
    LOGGER.debug(f"New deck [{deck.deck_id}]: {self.title}")

    for note in self.notes.values():
      note.add_to_deck(deck)
      LOGGER.debug(f"Added note {note.note_id}: {note.fields}")

      for field in note.fields:
        for media_path in field.media_paths():
          package.media_files.append(media_path)
          LOGGER.debug(f"Added media file for {note.note_id}: {media_path}")

    package.decks.append(deck)

  def save_to_file(self, path=None):
    if not path:
      path = os.path.splitext(self.source)[0] + '.apkg'

    package = genanki.Package([])
    self.save_to_package(package)
    package.write_to_file(path)
    LOGGER.info(f"Wrote deck {self.title} to file {path}")

    return path

class DeckParser:
  def __init__(self, cache_path):
    self.cache_path = cache_path
    self.parsed = []
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
      self.parsed.append(self.deck)

    self.deck = None
    self.path = None
    self.line_number = None
    self.note = []

  def flush_parsed(self):
    parsed = self.parsed
    self.parsed = []
    return parsed

  def where(self):
    return f"{self.path}, line {self.line_number}"

  def parse_input(self, input):
    """Takes FileInput as parameter."""
    for line in input:
      self.parse_line(input.filename(), input.filelineno(), line)
      for deck in self.flush_parsed():
        yield deck

    self.close()
    for deck in self.flush_parsed():
      yield deck

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
    elif line.startswith("format:"):
      self.deck.format = line.removeprefix("format:").strip()
    elif line.startswith("slow:"):
      self.deck.add_slow(line.removeprefix("slow:").strip())
    elif line.startswith("audio:"):
      self.deck.set_audio(line.removeprefix("audio:").strip())
    elif line.startswith("video"):
      self.deck.set_video(line.removeprefix("video:").strip())
    else:
      self.note.append(line)

  def _parse_note(self):
    try:
      [video_url, *rest] = "".join(self.note).split(maxsplit=1)
    except ValueError:
      # FIXME improve exception?
      raise ValueError(f'_parse_note() called on empty input ({self.where()})')

    if len(rest) > 0:
      rest = rest[0]
    else:
      rest = ''

    video = Video(video_url, cache_path=self.cache_path)
    video.audio(self.deck.audio)
    video.video(self.deck.video)
    if self.deck.crop:
      video.crop(self.deck.crop)
    if self.deck.format:
      video.format(self.deck.format)

    # Check for @time or @start-end
    rest = self._try_parse_clip(rest, video)

    # Check for a direction sign
    direction = '<->'
    if rest == '':
      question = video.title()
    else:
      parts = rest.split(maxsplit=1)
      if len(parts) >= 2 and parts[0] in ['->', '<-', '<->']:
        direction = parts[0]
        question = parts[1]
      else:
        question = rest

    # Figure out note_id
    if video.is_still():
      time = video.ffmpeg_input_options().get('ss', '0F')
      note_id = f'{video_url} @{time} {direction}'
    else:
      # Default to no clipping.
      start = video.ffmpeg_input_options().get('ss', '0F')
      end = video.ffmpeg_output_options().get('to', '')
      note_id = f'{video_url} @{start}-{end} {direction}'

    if self.deck.slow:
      (start, end, amount) = self.deck.slow
      video.slow_filter(start=start, end=end, amount=amount)

    path = video.processed_video()
    if video.is_still() or video.output_ext() == "gif":
      answer = ImageField(path)
    else:
      answer = VideoField(path)

    self.deck.add_note(
      Note(note_id, [Field(question), answer], self.deck.tags, direction))

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
