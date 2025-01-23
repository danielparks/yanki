import dataclasses
import functools

from yanki.errors import DeckSyntaxError
from yanki.parser.config import NoteConfigFrozen


@dataclasses.dataclass(frozen=True)
class NoteSpec:
    source_path: str
    line_number: int
    source: str  # config directives are stripped from this
    config: NoteConfigFrozen

    @functools.cache
    def provisional_note_id(self, deck_id="{deck_id}"):
        return self.config.generate_note_id(**self.variables(deck_id=deck_id))

    @functools.cache
    def variables(self, deck_id="{deck_id}"):
        """Get variables related to this note, including config variables."""
        return {
            **self.config.variables(),
            "deck_id": deck_id,
            "url": self.video_url(),
            "clip": self.provisional_clip_spec(),
            "direction": self.direction(),
            "media": " ".join([self.video_url(), self.provisional_clip_spec()]),
            "text": self.text(),
            "line_number": self.line_number,
            "source_path": self.source_path,
        }

    def video_url(self):
        return self._parse_video_url()[0]

    @functools.cache
    def _parse_video_url(self):
        try:
            [video_url, *rest] = self.source.rstrip().split(maxsplit=1)
        except ValueError:
            self.error("NoteSpec given empty source")

        return video_url, "".join(rest)  # rest is either [] or [str]

    def clip(self):
        return self._parse_clip()[0]

    @functools.cache
    def _parse_clip(self):
        input = self._parse_video_url()[1]
        if not input.startswith("@"):
            return None, input

        [raw_clip, *rest] = input.split(maxsplit=1)
        clip = raw_clip.removeprefix("@").split("-")

        if len(clip) == 2:
            if clip[0] == "":
                clip[0] = "0"
        elif len(clip) != 1 or clip[0] == "":
            self.error(f"Invalid clip specification {raw_clip!r}")

        return clip, "".join(rest)  # rest is either [] or [str]

    def direction(self):
        return self._parse_direction()[0]

    def text(self):
        return self._parse_direction()[1]

    @functools.cache
    def _parse_direction(self):
        input = self._parse_clip()[1]

        try:
            [direction, *rest] = input.split(maxsplit=1)
            if direction in ["->", "<-", "<->"]:
                return direction, "".join(rest)  # rest is either [] or [str]
        except ValueError:
            pass

        return "<->", input

    def provisional_clip_spec(self):
        if self.clip() is None:
            return "@0-"
        else:
            return f"@{'-'.join(self.clip())}"

    def error(self, message):
        raise DeckSyntaxError(message, self.source_path, self.line_number)


class DeckSpec:
    def __init__(self, source_path):
        self.title = None
        self.source_path = source_path
        self.note_specs = []
        # For debugging only:
        self.config = None

    def add_note_spec(self, note_spec: NoteSpec):
        self.note_specs.append(note_spec)
