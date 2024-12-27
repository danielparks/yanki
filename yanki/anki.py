import functools
import genanki
import hashlib
import logging
import os
import sys

from yanki.field import Fragment, ImageFragment, VideoFragment, Field
from yanki.parser import Config, NoteSpec, DeckSpec
from yanki.video import Video

LOGGER = logging.getLogger(__name__)

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
    if self.spec.direction() == '<->':
      text_to_media = '1'
      media_to_text = '1'
    elif self.spec.direction() == '<-':
      text_to_media = '1'
    elif self.spec.direction() == '->':
      media_to_text = '1'
    else:
      raise ValueError(f'Invalid direction {repr(self.spec.direction())}')

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
    return self.spec.config.generate_note_id(
      deck_id=deck_id,
      url=self.spec.video_url(),
      clip=self.clip_spec(),
      direction=self.spec.direction(),
      ### FIXME should these be renamed to clarify that they’re normalized
      ### versions of the input text?
      media=' '.join([self.spec.video_url(), self.clip_spec()]),
      text=self.text(),
    )

  @functools.cache
  def clip_spec(self):
    if self.spec.clip() is None:
      return '@0-'
    elif len(self.spec.clip()) in (1, 2):
      clip = [self.video().normalize_time_spec(t) for t in self.spec.clip()]
      return f'@{"-".join(clip)}'
    else:
      raise ValueError(f'Invalid clip: {repr(self.spec.clip())}')

  def text(self):
    if self.spec.text() == '':
      return self.video().title()
    else:
      return self.spec.text()

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
      video = Video(self.spec.video_url(), cache_path=self.spec.cache_path)
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

    if self.spec.clip() is not None:
      if self.spec.config.trim is not None:
        self.spec.error(f'Clip ({repr(self.spec.provisional_clip_spec())}) is '
          "incompatible with 'trim:'.")

      if len(self.spec.clip()) == 1:
        video.snapshot(self.spec.clip()[0])
      elif len(self.spec.clip()) == 2:
        video.clip(self.spec.clip()[0], self.spec.clip()[1])
      else:
        raise ValueError(f'Invalid clip: {repr(self.spec.clip())}')

    return video

class Deck:
  def __init__(self, spec: DeckSpec):
    self.spec = spec
    self.notes = dict()
    for note_spec in spec.note_specs:
      self.add_note(Note(note_spec))

  def title(self):
    return self.spec.config.title

  def source_path(self):
    return self.spec.source_path

  def add_note(self, note):
    id = note.note_id()
    if id in self.notes:
      note.spec.error(f'Note with id {repr(id)} already exists in deck')
    self.notes[id] = note

  def save_to_package(self, package):
    deck = genanki.Deck(name_to_id(self.title()), self.title())
    LOGGER.debug(f'New deck [{deck.deck_id}]: {self.title()}')

    for note in self.notes.values():
      note.add_to_deck(deck)
      LOGGER.debug(f'Added note {repr(note.note_id())}: {note.content_fields()}')

      for media_path in note.media_paths():
        package.media_files.append(media_path)
        LOGGER.debug(f'Added media file for {repr(note.note_id())}: {media_path}')

    package.decks.append(deck)

  def save_to_file(self, path=None):
    if not path:
      path = os.path.splitext(self.source_path())[0] + '.apkg'

    package = genanki.Package([])
    self.save_to_package(package)
    package.write_to_file(path)
    LOGGER.info(f'Wrote deck {self.title()} to file {path}')

    return path
