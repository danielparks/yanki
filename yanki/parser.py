from dataclasses import dataclass, field
import functools

from yanki.field import Fragment, Field

# Valid variables in note_id format. Used to validate that our code uses the
# same variables in both places they’re needed.
NOTE_ID_VARIABLES = frozenset([
  'deck_id', 'url', 'clip', 'direction', 'media', 'text',
])

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
    self.note_id_format = '{deck_id}__{url} {clip} {direction}'

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

  def set_note_id_format(self, note_id_format):
    try:
      note_id_format.format(**dict.fromkeys(NOTE_ID_VARIABLES, 'value'))
    except KeyError as error:
      raise ValueError(f'Unknown variable in note_id format: {error}')
    self.note_id_format = note_id_format

  def generate_note_id(self, **kwargs):
    if len(NOTE_ID_VARIABLES.symmetric_difference(kwargs.keys())) > 0:
      raise KeyError('Incorrect variables passed to generate_note_id()\n'
        f'  got: {sorted(kwargs.keys())}\n'
        f'  expected: {sorted(NOTE_ID_VARIABLES)}\n')
    return self.note_id_format.format(**kwargs)

@dataclass(frozen=True)
class NoteSpec:
  source_path: str
  line_number: int
  source: str # config directives are stripped from this
  config: Config
  cache_path: str

  def video_url(self):
    return self._parse_video_url()[0]

  @functools.cache
  def _parse_video_url(self):
    try:
      [video_url, *rest] = self.source.rstrip().split(maxsplit=1)
    except ValueError:
      self.error(f'NoteSpec given empty source')

    return video_url, ''.join(rest) # rest is either [] or [str]

  def clip(self):
    return self._parse_clip()[0]

  @functools.cache
  def _parse_clip(self):
    input = self._parse_video_url()[1]
    if not input.startswith('@'):
      return None, input

    [raw_clip, *rest] = input.split(maxsplit=1)
    clip = raw_clip.removeprefix('@').split('-')

    if len(clip) == 2:
      if clip[0] == '':
        clip[0] = '0'
    elif len(clip) != 1 or clip[0] == '':
      self.error(f'Invalid clip specification {repr(raw_clip)}')

    return clip, ''.join(rest) # rest is either [] or [str]

  def direction(self):
    return self._parse_direction()[0]

  def text(self):
    return self._parse_direction()[1]

  @functools.cache
  def _parse_direction(self):
    input = self._parse_clip()[1]

    try:
      [direction, *rest] = input.split(maxsplit=1)
      if direction in ['->', '<-', '<->']:
        return direction, ''.join(rest) # rest is either [] or [str]
    except ValueError:
      pass

    return '<->', input

  def provisional_clip_spec(self):
    if self.clip() is None:
      return '@0-'
    else:
      return f'@{"-".join(self.clip())}'

  def error(self, message):
    sys.exit(f"Error in {self.where()}: {message}")

  def where(self):
    return f"{self.source_path}, line {self.line_number}"
