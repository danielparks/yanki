from copy import copy, deepcopy
from dataclasses import dataclass, field
import docutils.core
import functools
import genanki
import hashlib
import html
import logging
import os
import re
import sys

from yanki.video import Video

LOGGER = logging.getLogger(__name__)

# Regular expression to find http:// URLs in text.
URL_FINDER = re.compile(r'''
  # URL with no surrounding parentheses
  (?<!\() \b(https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-])
  # URL with surrounding parentheses
  | (?<=\() (https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-]) (?=\))
  # URL with an initial parenthesis
  | (?<=\() (https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-]) (?!\))
''', flags=re.IGNORECASE | re.VERBOSE)

# Keep these variables local
def yanki_card_model():
  field_base = 7504631604350024486
  back_template = '''
    {{FrontSide}}

    <hr id="answer">

    <p>{{$FIELD}}</p>

    {{#More}}
    <div class="more">{{More}}</div>
    {{/More}}
  '''.replace('\n    ', '\n').strip()

  return genanki.Model(
    1221938102,
    'Optionally Bidirectional (yanki)',
    fields=[
      # The first field is the one displayed when browsing cards.
      { 'name': 'Text', 'id': field_base+1, 'font': 'Arial' },
      { 'name': 'More', 'id': field_base+4, 'font': 'Arial' },
      { 'name': 'Media', 'id': field_base+0, 'font': 'Arial' },
      { 'name': 'Text to media', 'id': field_base+2, 'font': 'Arial' }, # <-
      { 'name': 'Media to text', 'id': field_base+3, 'font': 'Arial' }, # ->
    ],
    templates=[
      {
        'name': 'Text to media', # <-
        'id': 6592322563225791602,
        'qfmt': '{{#Text to media}}<p>{{Text}}</p>{{/Text to media}}',
        'afmt': back_template.replace('$FIELD', 'Media'),
      },
      {
        'name': 'Media to text', # ->
        'id': 6592322563225791603,
        'qfmt': '{{#Media to text}}<p>{{Media}}</p>{{/Media to text}}',
        'afmt': back_template.replace('$FIELD', 'Text'),
      },
    ],
    css='''
      .card {
        font: 20px sans-serif;
        text-align: center;
        color: #000;
        background-color: #fff;
      }

      .more {
        font-size: 16px;
      }
    ''',
  )

YANKI_CARD_MODEL = yanki_card_model()

def name_to_id(name):
  bytes = hashlib.sha256(name.encode('utf-8')).digest()
  # Apparently deck ID is i64
  return int.from_bytes(bytes[:8], byteorder='big', signed=True)

def rst_to_html(rst):
  # From https://wiki.python.org/moin/reStructuredText#The_.22Cool.22_Way
  parts = docutils.core.publish_parts(source=rst, writer_name='html5')
  return parts['body_pre_docinfo'] + parts['fragment']

def raw_to_html(raw):
  if raw.startswith('rst:'):
    return rst_to_html(raw[4:])
  elif raw.startswith('html:'):
    return raw[5:]
  else:
    return URL_FINDER.sub(r'<a href="\1">\1</a>', html.escape(raw)) \
      .rstrip().replace("\n", "<br/>")

class Fragment:
  def __init__(self, raw):
    self.raw = raw

  def media_paths(self):
    return []

  def render_anki(self):
    return self.render_html('')

  def render_html(self, base_path=''):
    return raw_to_html(self.raw)

  def __str__(self):
    return self.render_anki()

  def __repr__(self):
    return repr(self.render_anki())

class MediaFragment(Fragment):
  def __init__(self, path):
    self.path = path

  def path_in_base(self, base_path):
    return os.path.join(base_path, os.path.basename(self.path))

  def media_paths(self):
    return [self.path]

class ImageFragment(MediaFragment):
  def render_html(self, base_path=''):
    media_filename_html = html.escape(self.path_in_base(base_path))
    return f'<img src="{media_filename_html}" />'

class VideoFragment(MediaFragment):
  def render_anki(self):
    media_filename_html = html.escape(self.path_in_base(''))
    return f"[sound:{media_filename_html}]"

  def render_html(self, base_path='.'):
    media_filename_html = html.escape(self.path_in_base(base_path))
    return f'<video controls src="{media_filename_html}"></video>'

class Field:
  def __init__(self, fragments: list[Fragment] = []):
    self.fragments = fragments

  def add_fragment(self, fragment: Fragment):
    self.fragments.append(fragment)

  def media_paths(self):
    for fragment in self.fragments:
      for path in fragment.media_paths():
        yield path

  def render_anki(self):
    return ''.join([fragment.render_anki() for fragment in self.fragments])

  def render_html(self, base_path=''):
    return ''.join([fragment.render_html(base_path) for fragment in self.fragments])

  def __str__(self):
    return self.render_anki()

  def __repr__(self):
    return repr([fragment for fragment in self.fragments])

class Config:
  def __init__(self):
    self.title = None
    self.crop = None
    self.format = None
    self.more = Field()
    self.overlay_text = ''
    self.tags = []
    self.slow = None
    self.trim = None
    self.audio = 'include'
    self.video = 'include'
    self.note_id = '{deck_id}__{url} {clip} {direction}'

  def set_more(self, input):
    self.more = Field([Fragment(input)])

  def add_more(self, input):
    self.more.add_fragment(Fragment(input))

  def set_overlay_text(self, input):
    self.overlay_text = input

  def update_tags(self, input):
    new_tags = input.split()
    found_bare_tag = False

    for tag in new_tags:
      if tag.startswith('+'):
        self.tags.append(tag[1:])
        new_tags = None
      elif tag.startswith('-'):
        try:
          self.tags.remove(tag[1:])
        except ValueError:
          pass
        new_tags = None
      else:
        # A tag without a + or - prefix, which implies we’re replacing all tags.
        # FIXME: quoting so a tag with a + or - prefix can be used easily.
        found_bare_tag = True

    if found_bare_tag:
      if new_tags is None:
        raise ValueError(
          f'Invalid mix of changing tags with setting tags: {input.strip()}')
      self.tags = new_tags

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

  def set_note_id(self, note_id_format):
    try:
      note_id_format.format(
        deck_id='deck_id',
        url='url',
        clip='@clip',
        direction='<->',
        media='media',
        text='text',
      )
    except KeyError as error:
      raise ValueError(f'Unknown variable in note_id format: {error}')
    self.note_id = note_id_format

@dataclass
class NoteSpec:
  source_path: str
  line_number: int
  source: str # config directives are stripped from this
  config: Config
  cache_path: str
  video_url: str = field(init=False)
  text: str = field(init=False)
  clip: list[str] | None = field(default=None, init=False) # FIXME type?
  direction: str = field(default='<->', init=False) # FIXME type?

  # May be called before __post_init__ finishes
  def error(self, message):
    sys.exit(f"Error in {self.where()}: {message}")

  # May be called before __post_init__ finishes
  def where(self):
    return f"{self.source_path}, line {self.line_number}"

  # May be called before __post_init__ finishes
  def _try_parse_clip(self, input):
    if not input.startswith('@'):
      return input

    [clip, *rest] = input.split(maxsplit=1)
    self.clip = clip.removeprefix('@').split('-')

    if len(self.clip) == 2:
      if self.clip[0] == '':
        self.clip[0] = '0'
    elif len(self.clip) != 1 or self.clip[0] == '':
      self.error(f'Invalid clip specification {repr(clip)}')

    return ''.join(rest) # rest is either [] or [str]

  # May be called before __post_init__ finishes
  def _try_parse_direction(self, input):
    parts = input.split(maxsplit=1)
    if len(parts) >= 1 and parts[0] in ['->', '<-', '<->']:
      self.direction = parts[0]
      if len(parts) >= 2:
        return parts[1]
      else:
        return ''
    else:
      return input

  def __post_init__(self):
    try:
      [self.video_url, *rest] = self.source.split(maxsplit=1)
    except ValueError:
      self.error(f'NoteSpec given empty source')

    if len(rest) > 0:
      # Remove trailing whitespace, particularly newlines.
      rest = rest[0].rstrip()
    else:
      rest = ''

    # Check for @time or @start-end
    rest = self._try_parse_clip(rest)
    if self.clip is not None and self.config.trim is not None:
      self.error(f'Clip ({repr(self.provisional_clip_spec())}) is '
        "incompatible with 'trim:'")

    # Check for a direction sign
    self.text = self._try_parse_direction(rest)

  def provisional_clip_spec(self):
    if self.clip is None:
      return '@0-'
    elif len(self.clip) in (1, 2):
      return f'@{"-".join(self.clip)}'
    else:
      raise ValueError(f'Invalid clip: {repr(clip)}')

class Note:
  def __init__(self, spec):
    self.spec = spec

  def media_paths(self):
    for field in self.content_fields():
      for path in field.media_paths():
        yield path

  def content_fields(self):
    return [self.text_field(), self.more_field(), self.media_field()]

  @functools.cache
  def text_field(self):
    return Field([Fragment(self.text())])

  @functools.cache
  def more_field(self):
    return self.spec.config.more

  @functools.cache
  def media_field(self):
    return Field([self.media_fragment()])

  def add_to_deck(self, deck):
    media_to_text = text_to_media = ''
    if self.spec.direction == '<->':
      text_to_media = '1'
      media_to_text = '1'
    elif self.spec.direction == '<-':
      text_to_media = '1'
    elif self.spec.direction == '->':
      media_to_text = '1'
    else:
      raise ValueError(f'Invalid direction {repr(self.spec.direction)}')

    deck.add_note(genanki.Note(
      model=YANKI_CARD_MODEL,
      fields=[
        self.text_field().render_anki(),
        self.more_field().render_anki(),
        self.media_field().render_anki(),
        text_to_media,
        media_to_text,
      ],
      guid=genanki.guid_for(self.note_id(deck.deck_id)),
      tags=self.spec.config.tags,
    ))

  # {deck_id} is just a placeholder. To get the real note_id, you need to have
  # a deck_id.
  @functools.cache
  def note_id(self, deck_id='{deck_id}'):
    return self.spec.config.note_id.format(
      deck_id=deck_id,
      url=self.spec.video_url,
      clip=self.clip_spec(),
      direction=self.spec.direction,
      ### FIXME should these be renamed to clarify that they’re normalized
      ### versions of the input text?
      media=' '.join([self.spec.video_url, self.clip_spec()]),
      text=self.text(),
    )

  @functools.cache
  def clip_spec(self):
    if self.spec.clip is None:
      return '@0-'
    elif len(self.spec.clip) in (1, 2):
      clip = [self.video().normalize_time_spec(part) for part in self.spec.clip]
      return f'@{"-".join(clip)}'
    else:
      raise ValueError(f'Invalid clip: {repr(self.spec.clip)}')

  def text(self):
    if self.spec.text == '':
      return self.video().title()
    else:
      return self.spec.text

  @functools.cache
  def media_fragment(self):
    path = self.video().processed_video()
    if self.video().is_still() or self.video().output_ext() == "gif":
      return ImageFragment(path)
    else:
      return VideoFragment(path)

  @functools.cache
  def video(self):
    try:
      video = Video(self.spec.video_url, cache_path=self.spec.cache_path)
      video.audio(self.spec.config.audio)
      video.video(self.spec.config.video)
      if self.spec.config.crop:
        video.crop(self.spec.config.crop)
      if self.spec.config.trim:
        video.clip(self.spec.config.trim[0], self.spec.config.trim[1])
      if self.spec.config.format:
        video.format(self.spec.config.format)
      if self.spec.config.slow:
        (start, end, amount) = self.spec.config.slow
        video.slow_filter(start=start, end=end, amount=amount)
      if self.spec.config.overlay_text:
        video.overlay_text(self.spec.config.overlay_text)
    except ValueError as error:
      self.spec.error(error)

    if self.spec.clip is not None:
      if self.spec.config.trim is not None:
        self.spec.error(f'Clip ({repr(self.spec.provisional_clip_spec())}) is '
          "incompatible with 'trim:'.")

      if len(self.spec.clip) == 1:
        video.snapshot(self.spec.clip[0])
      elif len(self.spec.clip) == 2:
        video.clip(self.spec.clip[0], self.spec.clip[1])
      else:
        raise ValueError(f'Invalid clip: {repr(self.spec.clip)}')

    return video

class Deck:
  def __init__(self, source=None):
    self.source = source
    self.config = Config()
    self.notes = {}

  def add_note(self, note):
    id = note.note_id()
    if id in self.notes:
      raise LookupError(f'Note with id {repr(id)} already exists in deck')
    self.notes[id] = note

  def save_to_package(self, package):
    deck = genanki.Deck(name_to_id(self.config.title), self.config.title)
    LOGGER.debug(f"New deck [{deck.deck_id}]: {self.config.title}")

    for note in self.notes.values():
      note.add_to_deck(deck)
      LOGGER.debug(f"Added note {repr(note.note_id())}: {note.content_fields()}")

      for media_path in note.media_paths():
        package.media_files.append(media_path)
        LOGGER.debug(f"Added media file for {repr(note.note_id())}: {media_path}")

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
    self.finished_decks = []
    self._reset()

  def _reset(self):
    self.deck = None
    self.path = None
    self.line_number = None
    self._reset_note()

  def _reset_note(self):
    self.note_source = []
    self.note_config = None

  def open(self, path):
    if self.deck:
      self.close()
    self._reset()
    self.deck = Deck(path)
    self.path = path

  def close(self):
    if len(self.note_source) > 0:
      self._add_note_to_deck(Note(self._finish_note()))
    if self.deck:
      self.finished_decks.append(self.deck)

    self._reset()

  def flush_decks(self):
    finished_decks = self.finished_decks
    self.finished_decks = []
    return finished_decks

  def error(self, message):
    sys.exit(f"Error in {self.where()}: {message}")

  def where(self):
    return f"{self.path}, line {self.line_number}"

  def parse_input(self, input):
    """Takes FileInput as parameter."""
    for line in input:
      self.parse_line(input.filename(), input.filelineno(), line)
      for deck in self.flush_decks():
        yield deck

    self.close()
    for deck in self.flush_decks():
      yield deck

  def parse_line(self, path, line_number, line):
    if not self.deck or self.path != path:
      self.open(path)

    self.line_number = line_number

    if line.startswith('#'):
      # Comment; skip line.
      return

    unindented = line.lstrip(' \t')
    if line != unindented:
      # Line is indented and thus a continuation of a note
      if len(self.note_source) == 0:
        self.error('Found indented line with no preceding unindented line')

      if self.note_config is None:
        self.note_config = deepcopy(self.deck.config)

      unindented = self._check_for_config(unindented, self.note_config)
      if unindented is not None:
        self.note_source.append(unindented)
      return

    if line.strip() == '':
      # Blank lines only count inside notes.
      if len(self.note_source) > 0:
        self.note_source.append(line)
      return

    # Line is not indented
    if len(self.note_source) > 0:
      self._add_note_to_deck(Note(self._finish_note()))

    line = self._check_for_config(line, self.deck.config)
    if line is not None:
      self.note_source.append(line)

  def _check_for_config(self, line, config):
    # Line without newline
    line_chomped = line.rstrip('\n\r')

    if line.startswith('"') and line_chomped.endswith('"'):
      # Quotes mean to use the line as-is (add the newline back):
      return line_chomped[1:-1] + line[len(line_chomped):]

    try:
      if line.startswith('title:'):
        config.title = line.removeprefix('title:').strip()
      elif line.startswith('more:'):
        config.set_more(line.removeprefix('more:').strip())
      elif line.startswith('more+'):
        config.add_more(line.removeprefix('more+').strip())
      elif line.startswith('overlay_text:'):
        config.set_overlay_text(line.removeprefix('overlay_text:').strip())
      elif line.startswith('tags:'):
        config.update_tags(line.removeprefix('tags:'))
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
        config.set_note_id(line.removeprefix('note_id:').strip())
      else:
        return line
    except ValueError as error:
      self.error(error)

    return None

  def _finish_note(self):
    spec = NoteSpec(
      # FIXME is self.note_config is None possible?
      config=self.note_config or deepcopy(self.deck.config),
      source_path=self.path,
      line_number=self.line_number,
      source=''.join(self.note_source),
      cache_path=self.cache_path,
    )
    self._reset_note()
    return spec

  def _add_note_to_deck(self, note):
    try:
      self.deck.add_note(note)
    except LookupError as error:
      self.error(error)
