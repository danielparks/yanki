import asyncio
import functools
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import genanki

from yanki.field import Field, Fragment, ImageFragment, VideoFragment
from yanki.parser import NOTE_VARIABLES, DeckSpec, NoteSpec
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

    async def finalize_async(self, deck_id):
        video = await self.video().finalize_async()
        media_path = await video.processed_video_async()

        if video.is_still() or video.output_ext() == "gif":
            media_fragment = ImageFragment(media_path, video)
        else:
            media_fragment = VideoFragment(media_path, video)

        note_id = self.note_id(deck_id)
        return FinalNote(
            note_id=note_id,
            deck_id=str(deck_id),
            media_fragment=media_fragment,
            text=self.text(),
            spec=self.spec,
            clip_spec=self.clip_spec(),
            logger=logging.getLogger(f"FinalNote[{note_id}]"),
        )

    @functools.cache
    def video(self):
        try:
            video = Video(
                self.spec.video_url(),
                working_dir=Path(self.spec.source_path).parent,
                options=self.video_options,
                logger=self.logger,
            )
            video.audio(self.spec.config.audio)
            video.video(self.spec.config.video)
            if self.spec.config.crop:
                video.crop(self.spec.config.crop)
            if self.spec.config.format:
                video.format(self.spec.config.format)
            if self.spec.config.slow:
                (start, end, amount) = self.spec.config.slow
                video.slow(start=start, end=end, amount=amount)
            if self.spec.config.overlay_text:
                video.overlay_text(self.spec.config.overlay_text)
        except ValueError as error:
            self.spec.error(error)

        clip = self.spec.clip_or_trim()
        if clip is not None:
            if len(clip) == 1:
                video.snapshot(clip[0])
            elif len(clip) == 2:
                video.clip(clip[0], clip[1])
            else:
                self.spec.error(f"Invalid clip: {clip!r}")

        return video

    # {deck_id} is just a placeholder. To get the real note_id, you need to have
    # a deck_id.
    def note_id(self, deck_id="{deck_id}"):
        return self.spec.config.generate_note_id(
            **self.variables(deck_id=deck_id),
        )

    def variables(self, deck_id="{deck_id}"):
        return {
            **self.spec.variables(),
            "deck_id": deck_id,
            "clip": self.clip_spec(),
            "media": f"{self.spec.video_url()} {self.clip_spec()}",
            "text": self.text(),
        }

    @functools.cache
    def clip_spec(self):
        if self.spec.clip() is None:
            return "@0-"
        if len(self.spec.clip()) in {1, 2}:
            return "@" + "-".join(
                [
                    str(self.video().time_to_seconds(t, on_none=""))
                    for t in self.spec.clip()
                ]
            )
        raise ValueError(f"Invalid clip: {self.spec.clip()!r}")

    def text(self):
        if self.spec.text() == "":
            return self.video().title()
        return self.spec.text()


EXTRA_FINAL_NOTE_VARIABLES = frozenset(
    [
        "note_id",
        "media_paths",
        "video_parameters",
        "auto_crop",
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
    logger: logging.Logger

    def media(self):
        for field in self.content_fields():
            yield from field.media()

    def media_paths(self):
        for field in self.content_fields():
            yield from field.media_paths()

    def content_fields(self):
        return [self.text_field(), self.more_field(), self.media_field()]

    def text_field(self):
        return Field([Fragment(self.text)])

    def more_field(self):
        return self.spec.config.more

    def media_field(self):
        return Field([self.media_fragment])

    def variables(self):
        return {
            **self.spec.variables(),
            "deck_id": self.deck_id,
            "note_id": self.note_id,
            "clip": self.clip_spec,
            "media": f"{self.spec.video_url()} {self.clip_spec}",
            "text": self.text,
            "media_paths": " ".join(self.media_paths()),
            "auto_crop": " / ".join(
                [str(media.cropdetect()) for media in self.media()]
            ),
            "video_parameters": " / ".join(
                [" ".join(media.parameters_list()) for media in self.media()]
            ),
        }

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
            tags=self.spec.config.tags,
        )

    def to_dict(self, base_url=""):
        """Recursively convert to dict."""
        return {
            "deck_id": self.deck_id,
            "note_id": self.note_id,
            "text_html": self.text_field().render_html(base_url=base_url),
            "media_html": self.media_field().render_html(base_url=base_url),
            "more_html": self.more_field().render_html(base_url=base_url),
            "media_paths": sorted(self.media_paths()),
            "direction": self.spec.direction(),
            "tags": sorted(self.spec.config.tags),
            "video_url": self.spec.video_url(),
            "source_path": self.spec.source_path,
            "line_number": self.spec.line_number,
        }


@dataclass(frozen=True)
class FinalDeck:
    deck_id: int
    title: str
    source_path: str
    spec: DeckSpec
    notes_by_id: dict

    def id(self):
        return self.deck_id

    def notes(self):
        """Get notes in the same order as the .deck file."""
        return sorted(
            self.notes_by_id.values(),
            key=lambda n: n.spec.line_number,
        )

    def media_paths(self):
        """Get media paths used in this deck."""
        for note in self.notes_by_id.values():
            yield from note.media_paths()

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
        if path:
            path = Path(path)
        else:
            path = Path(self.source_path).with_suffix(".apkg")

        package = genanki.Package([])
        self.save_to_package(package)
        package.write_to_file(path)
        LOGGER.info(f"Wrote deck {self.title} to file {path}")

        return path

    def to_dict(self, base_url=""):
        """Recursively convert to dict."""
        return {
            "deck_id": self.deck_id,
            "title": self.title,
            "source_path": self.source_path,
            "notes": [note.to_dict(base_url=base_url) for note in self.notes()],
        }


class Deck:
    def __init__(
        self,
        spec: DeckSpec,
        video_options: VideoOptions,
    ):
        self.spec = spec
        self.video_options = video_options
        self.notes_by_id = {}
        for note_spec in spec.note_specs:
            self.add_note(Note(note_spec, video_options=video_options))

    async def finalize_async(self):
        async def finalize_note_async(collection, note, deck_id):
            final_note = await note.finalize_async(deck_id)
            collection[final_note.note_id] = final_note

        final_notes = {}
        async with asyncio.TaskGroup() as group:
            for note in self.notes():
                group.create_task(
                    finalize_note_async(final_notes, note, self.id())
                )

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
        return self.spec.title

    def source_path(self):
        return self.spec.source_path

    def notes(self):
        """Get notes in the same order as the .deck file."""
        return sorted(
            self.notes_by_id.values(),
            key=lambda n: n.spec.line_number,
        )

    def add_note(self, note):
        id = note.note_id()
        if id in self.notes_by_id:
            note.spec.error(f"Note with id {id!r} already exists in deck")
        self.notes_by_id[id] = note
