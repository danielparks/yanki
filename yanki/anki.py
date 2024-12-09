from copy import copy
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

class Config:
  def __init__(self):
    self.title = None
    self.crop = None
    self.format = None
    self.tags = []
    self.slow = None
    self.trim = None
    self.audio = 'include'
    self.video = 'include'
    self.note_id = '{url} {clip} {direction}'

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

  def set_trim(self, trim):
    if trim == '':
      self.trim = None
    else:
      clip = [part.strip() for part in trim.split('-')]
      if len(clip) != 2:
        raise ValueError(f'trim must be time-time (found {repr(trim)})')
      self.trim = (clip[0], clip[1])

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

class Deck:
  def __init__(self, source=None):
    self.source = source
    self.config = Config()
    self.notes = {}

  def add_note(self, note):
    if note.note_id in self.notes:
      raise LookupError(f"Note with id {repr(note.note_id)} already exists in deck")
    self.notes[note.note_id] = note

  def save_to_package(self, package):
    deck = genanki.Deck(name_to_id(self.config.title), self.config.title)
    LOGGER.debug(f"New deck [{deck.deck_id}]: {self.config.title}")

    for note in self.notes.values():
      note.add_to_deck(deck)
      LOGGER.debug(f"Added note {repr(note.note_id)}: {note.fields}")

      for field in note.fields:
        for media_path in field.media_paths():
          package.media_files.append(media_path)
          LOGGER.debug(f"Added media file for {repr(note.note_id)}: {media_path}")

    package.decks.append(deck)

  def save_to_file(self, path=None):
    if not path:
      path = os.path.splitext(self.source)[0] + '.apkg'

    package = genanki.Package([])
    self.save_to_package(package)
    package.write_to_file(path)
    LOGGER.info(f"Wrote deck {self.config.title} to file {path}")

    return path

class DeckParser:
  def __init__(self, cache_path):
    self.cache_path = cache_path
    self.parsed = []
    self._reset()

  def _reset(self):
    self.deck = None
    self.path = None
    self.line_number = None
    self._reset_note()

  def _reset_note(self):
    self.note = []
    self.note_config = None

  def open(self, path):
    if self.deck:
      self.close()
    self._reset()
    self.deck = Deck(path)
    self.path = path

  def close(self):
    if len(self.note) > 0:
      self._finish_note()
    if self.deck:
      self.parsed.append(self.deck)

    self._reset()

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

      if self.note_config is None:
        self.note_config = copy(self.deck.config)

      unindented = self._check_for_config(unindented, self.note_config)
      if unindented is not None:
        self.note.append(unindented)
      return

    if line.strip() == "":
      # Blank lines only count inside notes.
      if len(self.note) > 0:
        self.note.append(line)
      return

    # Line is not indented
    if len(self.note) > 0:
      self._finish_note()

    line = self._check_for_config(line, self.deck.config)
    if line is not None:
      self.note.append(line)

  def _check_for_config(self, line, config):
    # Line without newline
    line_per_se = line.rstrip('\n\r')

    if line.startswith('"') and line_per_se.endswith('"\n'):
      # Quotes mean to use the line as-is (add the newline back):
      return line_per_se[1:-1] + line[len(line_per_se):]

    # FIXME what about reseting the config for the next note?
    if line.startswith('title:'):
      config.title = line.removeprefix('title:').strip()
    elif line.startswith('tags:'):
      config.tags = line.removeprefix('tags:').split()
    elif line.startswith('crop:'):
      config.crop = line.removeprefix('crop:').strip()
    elif line.startswith('format:'):
      config.format = line.removeprefix('format:').strip()
    elif line.startswith('trim:'):
      config.set_trim(line.removeprefix('trim:').strip())
    elif line.startswith('slow:'):
      config.add_slow(line.removeprefix('slow:').strip())
    elif line.startswith('audio:'):
      config.set_audio(line.removeprefix('audio:').strip())
    elif line.startswith('video:'):
      config.set_video(line.removeprefix('video:').strip())
    elif line.startswith('note_id'):
      config.note_id = line.removeprefix('note_id:').strip()
    else:
      return line

    return None

  def _finish_note(self):
    try:
      [video_url, *rest] = "".join(self.note).split(maxsplit=1)
    except ValueError:
      # FIXME improve exception?
      raise ValueError(f'_finish_note() called on empty input ({self.where()})')

    if len(rest) > 0:
      rest = rest[0]
    else:
      rest = ''

    config = self.note_config or self.deck.config

    video = Video(video_url, cache_path=self.cache_path)
    video.audio(config.audio)
    video.video(config.video)
    if config.crop:
      video.crop(config.crop)
    if config.format:
      video.format(config.format)

    # Check for @time or @start-end
    (clip, rest) = self._try_parse_clip(rest)

    if clip is not None:
      if config.trim is not None:
        raise ValueError(f'Clip (@{"-".join(clip)}) is incompatible with trim')
      elif len(clip) == 1:
        video.snapshot(clip[0])
      elif len(clip) == 2:
        video.clip(clip[0], clip[1])
      else:
        # Should never happen — checked by _try_parse_clip()
        raise ValueError(f'Invalid clip (@{"-".join(clip)})')

      # Normalize clip for note_id
      clip = [video.parse_time_spec(part) for part in clip]

    if config.trim is not None:
      video.clip(config.trim[0], config.trim[1])

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

    # Remove trailing whitespace, particularly newlines.
    question = question.rstrip()

    if config.slow:
      (start, end, amount) = config.slow
      video.slow_filter(start=start, end=end, amount=amount)

    path = video.processed_video()
    if video.is_still() or video.output_ext() == "gif":
      answer = ImageField(path)
    else:
      answer = VideoField(path)

    # Format clip for note_id
    if clip is None:
      clip = '@0F-'
    else:
      clip = f'@{"-".join(clip)}'

    try:
      note_id = config.note_id.format(
        url=video_url,
        clip=clip,
        direction=direction,
        question=question,
      )
    except KeyError as error:
      # FIXME we don’t know the line number and filename for this since note_id
      # was set elsewhere.
      sys.exit(f'Unknown variable in note_id format: {error}')

    self.deck.add_note(
      Note(note_id, [Field(question), answer], config.tags, direction))
    self._reset_note()

  def _try_parse_clip(self, input):
    clip = None

    if not input.startswith("@"):
      return (clip, input)

    parts = input.split(maxsplit=1)
    if len(parts) >= 1:
      clip = parts[0].removeprefix("@").split("-")
      if len(clip) < 1 or len(clip) > 2:
        raise ValueError(f"Invalid clip specification {repr(parts[0])} ({self.where()})")

    # Return rest of input
    if len(parts) == 2:
      return (clip, parts[1])
    else:
      return (clip, "")
