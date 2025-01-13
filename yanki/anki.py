import asyncio
from dataclasses import dataclass
import functools
import genanki
import hashlib
import logging
import os
from pathlib import Path

from yanki.field import Fragment, ImageFragment, VideoFragment, Field
from yanki.parser import DeckSpec, NoteSpec, NOTE_VARIABLES
from yanki.video import Video, VideoOptions

LOGGER = logging.getLogger(__name__)


# Keep these variables local
def yanki_card_model():
    field_base = 7504631604350024486
    back_template = """
    {{FrontSide}}

    <hr id="answer">

    <p>{{$FIELD}}</p>

    {{#More}}
    <div class="more">{{More}}</div>
    {{/More}}
  """.replace("\n    ", "\n").strip()

    return genanki.Model(
        1221938102,
        "Optionally Bidirectional (yanki)",
        fields=[
            # The first field is the one displayed when browsing cards.
            {"name": "Text", "id": field_base + 1, "font": "Arial"},
            {"name": "More", "id": field_base + 4, "font": "Arial"},
            {"name": "Media", "id": field_base + 0, "font": "Arial"},
            {
                "name": "Text to media",
                "id": field_base + 2,
                "font": "Arial",
            },  # <-
            {
                "name": "Media to text",
                "id": field_base + 3,
                "font": "Arial",
            },  # ->
        ],
        templates=[
            {
                "name": "Text to media",  # <-
                "id": 6592322563225791602,
                "qfmt": "{{#Text to media}}<p>{{Text}}</p>{{/Text to media}}",
                "afmt": back_template.replace("$FIELD", "Media"),
            },
            {
                "name": "Media to text",  # ->
                "id": 6592322563225791603,
                "qfmt": "{{#Media to text}}<p>{{Media}}</p>{{/Media to text}}",
                "afmt": back_template.replace("$FIELD", "Text"),
            },
        ],
        css="""
      .card {
        font: 20px sans-serif;
        text-align: center;
        color: #000;
        background-color: #fff;
      }

      .more {
        font-size: 16px;
      }
    """,
    )


YANKI_CARD_MODEL = yanki_card_model()


def name_to_id(name):
    bytes = hashlib.sha256(name.encode("utf_8")).digest()
    # Apparently deck ID is i64
    return int.from_bytes(bytes[:8], byteorder="big", signed=True)


class Note:
    def __init__(self, spec, video_options: VideoOptions):
        self.spec = spec
        self.video_options = video_options
        self.logger = logging.getLogger(
            f"Note[{self.spec.provisional_note_id()}]"
        )

    async def finalize(self, deck_id):
        video = self.video()
        media_path = await video.processed_video_async()

        if video.is_still() or video.output_ext() == "gif":
            media_fragment = ImageFragment(media_path)
        else:
            media_fragment = VideoFragment(media_path)

        note_id = self.note_id(deck_id)
        return FinalNote(
            note_id=note_id,
            deck_id=str(deck_id),
            media_fragment=media_fragment,
            text=self.text(),
            spec=self.spec,
            clip_spec=self.clip_spec(),
            video=video,
            logger=logging.getLogger(f"FinalNote[{note_id}]"),
        )

    @functools.cache
    def video(self):
        deck_dir = os.path.dirname(self.spec.source_path)
        try:
            video = Video(
                self.spec.video_url(),
                working_dir=Path(deck_dir),
                options=self.video_options,
                logger=self.logger,
            )
            video.audio(self.spec.scope.audio)
            video.video(self.spec.scope.video)
            if self.spec.scope.crop:
                video.crop(self.spec.scope.crop)
            if self.spec.scope.trim:
                video.clip(self.spec.scope.trim[0], self.spec.scope.trim[1])
            if self.spec.scope.format:
                video.format(self.spec.scope.format)
            if self.spec.scope.slow:
                (start, end, amount) = self.spec.scope.slow
                video.slow(start=start, end=end, amount=amount)
            if self.spec.scope.overlay_text:
                video.overlay_text(self.spec.scope.overlay_text)
        except ValueError as error:
            self.spec.error(error)

        if self.spec.clip() is not None:
            if self.spec.scope.trim is not None:
                self.spec.error(
                    f"Clip ({self.spec.provisional_clip_spec()!r}) is "
                    "incompatible with 'trim:'."
                )

            if len(self.spec.clip()) == 1:
                video.snapshot(self.spec.clip()[0])
            elif len(self.spec.clip()) == 2:
                video.clip(self.spec.clip()[0], self.spec.clip()[1])
            else:
                raise ValueError(f"Invalid clip: {self.spec.clip()!r}")

        return video

    # {deck_id} is just a placeholder. To get the real note_id, you need to have
    # a deck_id.
    def note_id(self, deck_id="{deck_id}"):
        return self.spec.scope.generate_note_id(
            **self.variables(deck_id=deck_id),
        )

    def variables(self, deck_id="{deck_id}"):
        variables = {
            "deck_id": deck_id,
            "url": self.spec.video_url(),
            "clip": self.clip_spec(),
            "direction": self.spec.direction(),
            ### FIXME should these be renamed to clarify that they’re normalized
            ### versions of the input text?
            "media": f"{self.spec.video_url()} {self.clip_spec()}",
            "text": self.text(),
            "line_number": self.spec.line_number,
            "source_path": self.spec.source_path,
        }

        # FIXME: probably doesn’t need to run every time.
        if NOTE_VARIABLES != set(variables.keys()):
            raise KeyError(
                "Note.variables() does not match NOTE_VARIABLES\n"
                f"  variables(): {sorted(variables.keys())}\n"
                f"  expected: {sorted(NOTE_VARIABLES)}\n"
            )

        return variables

    @functools.cache
    def clip_spec(self):
        if self.spec.clip() is None:
            return "@0-"
        elif len(self.spec.clip()) in (1, 2):
            return "@" + "-".join(
                [
                    str(self.video().time_to_seconds(t, on_none=""))
                    for t in self.spec.clip()
                ]
            )
        else:
            raise ValueError(f"Invalid clip: {self.spec.clip()!r}")

    def text(self):
        if self.spec.text() == "":
            return self.video().title()
        else:
            return self.spec.text()


EXTRA_FINAL_NOTE_VARIABLES = frozenset(
    [
        "note_id",
        "media_paths",
    ]
)

FINAL_NOTE_VARIABLES = EXTRA_FINAL_NOTE_VARIABLES | NOTE_VARIABLES

if NOTE_VARIABLES & EXTRA_FINAL_NOTE_VARIABLES:
    raise KeyError(
        "Variables in both NOTE_VARIABLES and EXTRA_FINAL_NOTE_VARIABLES: "
        + ", ".join(sorted(NOTE_VARIABLES & EXTRA_FINAL_NOTE_VARIABLES))
    )


@dataclass(frozen=True)
class FinalNote:
    deck_id: str
    note_id: str
    media_fragment: Fragment
    text: str
    spec: NoteSpec
    clip_spec: str
    video: Video
    logger: logging.Logger

    def media_paths(self):
        for field in self.content_fields():
            for path in field.media_paths():
                yield path

    def content_fields(self):
        return [self.text_field(), self.more_field(), self.media_field()]

    def text_field(self):
        return Field([Fragment(self.text)])

    def more_field(self):
        return self.spec.scope.more

    def media_field(self):
        return Field([self.media_fragment])

    def variables(self):
        variables = {
            "deck_id": self.deck_id,
            "note_id": self.note_id,
            "url": self.spec.video_url(),
            "clip": self.clip_spec,
            "direction": self.spec.direction(),
            ### FIXME should these be renamed to clarify that they’re normalized
            ### versions of the input text?
            "media": f"{self.spec.video_url()} {self.clip_spec}",
            "text": self.text,
            "line_number": self.spec.line_number,
            "source_path": self.spec.source_path,
            "media_paths": " ".join(self.media_paths()),
        }

        # FIXME: probably doesn’t need to run every time.
        if FINAL_NOTE_VARIABLES != set(variables.keys()):
            raise KeyError(
                "FinalNote.variables() does not match FINAL_NOTE_VARIABLES\n"
                f"  variables(): {sorted(variables.keys())}\n"
                f"  expected: {sorted(FINAL_NOTE_VARIABLES)}\n"
            )

        return variables

    def genanki_note(self):
        media_to_text = text_to_media = ""
        if self.spec.direction() == "<->":
            text_to_media = "1"
            media_to_text = "1"
        elif self.spec.direction() == "<-":
            text_to_media = "1"
        elif self.spec.direction() == "->":
            media_to_text = "1"
        else:
            raise ValueError(f"Invalid direction {self.spec.direction()!r}")

        return genanki.Note(
            model=YANKI_CARD_MODEL,
            fields=[
                self.text_field().render_anki(),
                self.more_field().render_anki(),
                self.media_field().render_anki(),
                text_to_media,
                media_to_text,
            ],
            guid=genanki.guid_for(self.note_id),
            tags=self.spec.scope.tags,
        )


@dataclass(frozen=True)
class FinalDeck:
    deck_id: int
    title: str
    source_path: str
    spec: NoteSpec
    notes_by_id: dict

    def id(self):
        return self.deck_id

    def notes(self):
        """Returns notes in the same order as the .deck file."""
        return sorted(
            self.notes_by_id.values(),
            key=lambda n: n.spec.line_number,
        )

    def save_to_package(self, package):
        deck = genanki.Deck(self.deck_id, self.title)
        LOGGER.debug(f"New deck [{self.deck_id}]: {self.title}")

        for note in self.notes():
            deck.add_note(note.genanki_note())
            LOGGER.debug(
                f"Added note {note.note_id!r}: {note.content_fields()}"
            )

            for media_path in note.media_paths():
                package.media_files.append(media_path)
                LOGGER.debug(
                    f"Added media file for {note.note_id!r}: {media_path!r}"
                )

        package.decks.append(deck)

    def save_to_file(self, path=None):
        if not path:
            path = os.path.splitext(self.source_path)[0] + ".apkg"

        package = genanki.Package([])
        self.save_to_package(package)
        package.write_to_file(path)
        LOGGER.info(f"Wrote deck {self.title} to file {path}")

        return path


class Deck:
    def __init__(
        self,
        spec: DeckSpec,
        video_options: VideoOptions,
    ):
        self.spec = spec
        self.video_options = video_options
        self.notes_by_id = dict()
        for note_spec in spec.note_specs:
            self.add_note(Note(note_spec, video_options=video_options))

    async def finalize(self):
        async def finalize_note(collection, note, deck_id):
            final_note = await note.finalize(deck_id)
            collection[final_note.note_id] = final_note

        final_notes = dict()
        async with asyncio.TaskGroup() as group:
            for note in self.notes():
                group.create_task(finalize_note(final_notes, note, self.id()))

        return FinalDeck(
            deck_id=self.id(),
            title=self.title(),
            source_path=self.source_path(),
            spec=self.spec,
            notes_by_id=final_notes,
        )

    def id(self):
        return name_to_id(self.title())

    def title(self):
        return self.spec.scope.title

    def source_path(self):
        return self.spec.source_path

    def notes(self):
        """Returns notes in the same order as the .deck file."""
        return sorted(
            self.notes_by_id.values(),
            key=lambda n: n.spec.line_number,
        )

    def add_note(self, note):
        id = note.note_id()
        if id in self.notes_by_id:
            note.spec.error(f"Note with id {id!r} already exists in deck")
        self.notes_by_id[id] = note
