from copy import deepcopy
from dataclasses import dataclass
import functools

from yanki.field import Fragment, Field

# Valid variables in note_id format. Used to validate that our code uses the
# same variables in both places they’re needed.
NOTE_ID_VARIABLES = frozenset(
    [
        "deck_id",
        "url",
        "clip",
        "direction",
        "media",
        "text",
    ]
)


class SyntaxError(Exception):
    def __init__(self, message: str, source_path: str, line_number: int):
        self.message = message
        self.source_path = source_path
        self.line_number = line_number

    def __str__(self):
        return f"Error in {self.where()}: {self.message}"

    def where(self):
        return f"{self.source_path}, line {self.line_number}"


class Config:
    def __init__(self):
        self.title = None
        self.crop = None
        self.format = None
        self.more = Field()
        self.overlay_text = ""
        self.tags = []
        self.slow = None
        self.trim = None
        self.audio = "include"
        self.video = "include"
        self.note_id_format = "{deck_id} {url} {clip}"

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
            if tag.startswith("+"):
                self.tags.append(tag[1:])
                new_tags = None
            elif tag.startswith("-"):
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
                    f"Invalid mix of changing tags with setting tags: {input.strip()}"
                )
            self.tags = new_tags

    def add_slow(self, slow_spec):
        if slow_spec.strip() == "":
            self.slow = None
            return

        parts = [p.strip() for p in slow_spec.split("*")]
        if len(parts) != 2:
            raise ValueError(f"Invalid slow without '*': {slow_spec}")

        amount = float(parts[1])
        if amount < 0.01:
            raise ValueError(f"Cannot slow by less than 0.01: {slow_spec}")

        parts = [p.strip() for p in parts[0].split("-")]
        if len(parts) != 2:
            raise ValueError(f"Invalid slow without '-': {slow_spec}")

        # FIXME validate that end > start
        start = parts[0]
        if start == "":
            start = "0"

        end = parts[1]
        if end == "":
            end = None

        self.slow = (start, end, amount)

    def set_trim(self, trim):
        if trim == "":
            self.trim = None
        else:
            clip = [part.strip() for part in trim.split("-")]
            if len(clip) != 2:
                raise ValueError(f"trim must be time-time (found {repr(trim)})")
            self.trim = (clip[0], clip[1])

    def set_audio(self, audio):
        if audio == "include" or audio == "strip":
            self.audio = audio
        else:
            raise ValueError('audio must be either "include" or "strip"')

    def set_video(self, video):
        if video == "include" or video == "strip":
            self.video = video
        else:
            raise ValueError('video must be either "include" or "strip"')

    def set_note_id_format(self, note_id_format):
        try:
            note_id_format.format(**dict.fromkeys(NOTE_ID_VARIABLES, "value"))
        except KeyError as error:
            raise ValueError(f"Unknown variable in note_id format: {error}")
        self.note_id_format = note_id_format

    def generate_note_id(self, **kwargs):
        if len(NOTE_ID_VARIABLES.symmetric_difference(kwargs.keys())) > 0:
            raise KeyError(
                "Incorrect variables passed to generate_note_id()\n"
                f"  got: {sorted(kwargs.keys())}\n"
                f"  expected: {sorted(NOTE_ID_VARIABLES)}\n"
            )
        return self.note_id_format.format(**kwargs)


@dataclass(frozen=True)
class NoteSpec:
    source_path: str
    line_number: int
    source: str  # config directives are stripped from this
    config: Config

    @functools.cache
    def provisional_note_id(self, deck_id="{deck_id}"):
        return self.config.generate_note_id(
            deck_id=deck_id,
            url=self.video_url(),
            clip=self.provisional_clip_spec(),
            direction=self.direction(),
            media=" ".join([self.video_url(), self.provisional_clip_spec()]),
            text=self.text(),
        )

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
            self.error(f"Invalid clip specification {repr(raw_clip)}")

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
            return f'@{"-".join(self.clip())}'

    def error(self, message):
        raise SyntaxError(message, self.source_path, self.line_number)


class DeckSpec:
    def __init__(self, source_path):
        self.source_path = source_path
        self.config = Config()
        self.note_specs = []

    def add_note_spec(self, note_spec: NoteSpec):
        self.note_specs.append(note_spec)


class DeckParser:
    def __init__(self):
        self.finished_decks = []
        self._reset()

    def _reset(self):
        """Reset working deck data."""
        self.working_deck = None
        self.source_path = None
        self.line_number = None
        self._reset_note()

    def _reset_note(self):
        """Reset working note data."""
        self.note_source = []
        self.note_config = None

    def open(self, path):
        """Open a deck file for parsing."""
        if self.working_deck:
            self.close()
        self._reset()
        self.working_deck = DeckSpec(path)
        self.source_path = path

    def close(self):
        """Close deck file and mark working deck finished."""
        if len(self.note_source) > 0:
            self._finish_note()

        if self.working_deck.config.title is None:
            raise SyntaxError(
                "Does not contain title",
                self.working_deck.source_path,
                1,
            )
        self.finished_decks.append(self.working_deck)

        self._reset()

    def flush_decks(self):
        finished_decks = self.finished_decks
        self.finished_decks = []
        return finished_decks

    def error(self, message):
        raise SyntaxError(message, self.source_path, self.line_number)

    def parse_input(self, input):
        """Takes FileInput as parameter."""
        for line in input:
            self.parse_line(input.filename(), input.filelineno(), line)
            for deck_spec in self.flush_decks():
                yield deck_spec

        self.close()
        for deck_spec in self.flush_decks():
            yield deck_spec

    def parse_path(self, path):
        with open(path, "r", encoding="UTF-8") as input:
            for number, line in enumerate(input):
                self.parse_line(path, number + 1, line)

        self.close()
        return self.flush_decks()

    def parse_line(self, path, line_number, line):
        if not self.working_deck or self.source_path != path:
            self.open(path)

        self.line_number = line_number

        if line.startswith("#"):
            # Comment; skip line.
            return

        unindented = line.lstrip(" \t")
        if line != unindented:
            # Line is indented and thus a continuation of a note
            if len(self.note_source) == 0:
                self.error(
                    "Found indented line with no preceding unindented line"
                )

            if self.note_config is None:
                self.note_config = deepcopy(self.working_deck.config)

            unindented = self._check_for_config(unindented, self.note_config)
            if unindented is not None:
                self.note_source.append(unindented)
            return

        if line.strip() == "":
            # Blank lines only count inside notes.
            if len(self.note_source) > 0:
                self.note_source.append(line)
            return

        # Line is not indented
        if len(self.note_source) > 0:
            self._finish_note()

        line = self._check_for_config(line, self.working_deck.config)
        if line is not None:
            self.note_source.append(line)

    def _check_for_config(self, line, config):
        # Line without newline
        line_chomped = line.rstrip("\n\r")

        if line.startswith('"') and line_chomped.endswith('"'):
            # Quotes mean to use the line as-is (add the newline back):
            return line_chomped[1:-1] + line[len(line_chomped) :]

        try:
            if line.startswith("title:"):
                config.title = line.removeprefix("title:").strip()
            elif line.startswith("more:"):
                config.set_more(line.removeprefix("more:").strip())
            elif line.startswith("more+"):
                config.add_more(line.removeprefix("more+").strip())
            elif line.startswith("overlay_text:"):
                config.set_overlay_text(
                    line.removeprefix("overlay_text:").strip()
                )
            elif line.startswith("tags:"):
                config.update_tags(line.removeprefix("tags:"))
            elif line.startswith("crop:"):
                config.crop = line.removeprefix("crop:").strip()
            elif line.startswith("format:"):
                config.format = line.removeprefix("format:").strip()
            elif line.startswith("trim:"):
                config.set_trim(line.removeprefix("trim:").strip())
            elif line.startswith("slow:"):
                config.add_slow(line.removeprefix("slow:").strip())
            elif line.startswith("audio:"):
                config.set_audio(line.removeprefix("audio:").strip())
            elif line.startswith("video:"):
                config.set_video(line.removeprefix("video:").strip())
            elif line.startswith("note_id"):
                config.set_note_id_format(line.removeprefix("note_id:").strip())
            else:
                return line
        except ValueError as error:
            self.error(error)

        return None

    def _finish_note(self):
        self.working_deck.add_note_spec(
            NoteSpec(
                # FIXME is self.note_config is None possible?
                config=self.note_config or deepcopy(self.working_deck.config),
                source_path=self.source_path,
                line_number=self.line_number,
                source="".join(self.note_source),
            )
        )
        self._reset_note()
