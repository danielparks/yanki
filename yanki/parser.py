from copy import deepcopy
import dataclasses
from dataclasses import field
import functools
import inspect
import io
import logging
import re
import types
import typing

from yanki.errors import ExpectedError
from yanki.field import Fragment, Field
from yanki.utils import add_trace_logging

add_trace_logging()
LOGGER = logging.getLogger(__name__)


# Valid variables in note_id format. Used to validate that our code uses the
# same variables in both places they’re needed.
NOTE_VARIABLES = frozenset(
    [
        "deck_id",
        "url",
        "clip",
        "direction",
        "media",
        "text",
        "line_number",
        "source_path",
    ]
)

# Regular expression to identify config directives.
#
# Indentiation must be stripped first, and `fullmatch` must be used.
CONFIG_REGEX = re.compile(
    r"""
    # Config directive must start with a letter.
    ([a-z][a-z0-9._\[\]-]*):

    # The value must be separated from the colon by whitespace, but if there is
    # no value then whitespace is not required. (Consider a file that ends with
    # a config directive and then no newline.)
    (?:\s+(\S.*\s*)?)?
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def find_invalid_format(format, variables):
    """
    Try `format` and return `KeyError` if it uses anything not in `variables`.
    """
    try:
        format.format(**dict.fromkeys(variables, "value"))
        return None
    except KeyError as error:
        return error


class DeckSyntaxError(ExpectedError):
    def __init__(self, message: str, source_path: str, line_number: int):
        self.message = message
        self.source_path = source_path
        self.line_number = line_number

    def __str__(self):
        return f"Error in {self.where()}: {self.message}"

    def where(self):
        return f"{self.source_path}, line {self.line_number}"


@functools.cache
def note_config_directives():
    return set([field.name for field in dataclasses.fields(NoteConfig)])


@dataclasses.dataclass()
class NoteConfig:
    crop: str = ""
    format: str = ""
    more: Field = field(default_factory=Field)
    overlay_text: str = ""
    tags: set[str] = field(default_factory=set)
    slow: None | tuple[str, None | str, float] = None
    trim: None | tuple[str, str] = None
    audio: str = "include"
    video: str = "include"
    note_id: str = "{deck_id} {url} {clip}"

    def set(self, name, value):
        if name in note_config_directives():
            getattr(self, f"set_{name}")(value)
        else:
            raise ValueError(f"Invalid config directive {name!r}")

    def set_crop(self, input):
        self.crop = input

    def set_format(self, input):
        self.format = input

    def set_more(self, input):
        if input.startswith("+"):
            self.more.add_fragment(Fragment(input[1:]))
        else:
            self.more = Field([Fragment(input)])

    def set_overlay_text(self, input):
        if input.startswith("+"):
            self.overlay_text += input[1:]
        else:
            self.overlay_text = input

    def set_tags(self, input):
        new_tags = input.split()
        found_bare_tag = False

        for tag in new_tags:
            if tag.startswith("+"):
                self.tags.add(tag[1:])
                new_tags = None
            elif tag.startswith("-"):
                try:
                    self.tags.remove(tag[1:])
                except KeyError:
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
            self.tags = set(new_tags)

    def set_slow(self, slow_spec):
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
                raise ValueError(f"trim must be time-time (found {trim!r})")
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

    def set_note_id(self, note_id):
        if error := find_invalid_format(note_id, NOTE_VARIABLES):
            raise ValueError(f"Unknown variable in note_id format: {error}")
        self.note_id = note_id

    def frozen(self):
        data = dataclasses.asdict(self)
        data["tags"] = frozenset(data["tags"])
        return NoteConfigFrozen(**data)

    def generate_note_id(self, **kwargs):
        if NOTE_VARIABLES != set(kwargs.keys()):
            raise KeyError(
                "Incorrect variables passed to generate_note_id()\n"
                f"  got: {sorted(kwargs.keys())}\n"
                f"  expected: {sorted(NOTE_VARIABLES)}\n"
            )
        return self.note_id.format(**kwargs)


def make_frozen(klass):
    """Kludge to produce frozen version of dataclass."""

    name = klass.__name__ + "Frozen"
    fields = dataclasses.fields(klass)

    # This isn’t realliy necessary. It doesn’t check types. It also only handles
    # `set[...]` and not `None | set[...]`, etc.
    for f in fields:
        if typing.get_origin(f.type) is set:
            f.type = types.GenericAlias(frozenset, typing.get_args(f.type))

    namespace = {
        key: value
        for key, value in klass.__dict__.items()
        if inspect.isfunction(value)
        and key != "frozen"
        and not key.startswith("set")
        and not key.startswith("_")
    }

    return dataclasses.make_dataclass(
        name,
        fields=[(f.name, f.type, f) for f in fields],
        namespace=namespace,
        frozen=True,
    )


NoteConfigFrozen = make_frozen(NoteConfig)


@dataclasses.dataclass(frozen=True)
class NoteSpec:
    source_path: str
    line_number: int
    source: str  # config directives are stripped from this
    config: NoteConfigFrozen

    @functools.cache
    def provisional_note_id(self, deck_id="{deck_id}"):
        return self.config.generate_note_id(
            deck_id=deck_id,
            url=self.video_url(),
            clip=self.provisional_clip_spec(),
            direction=self.direction(),
            media=" ".join([self.video_url(), self.provisional_clip_spec()]),
            text=self.text(),
            line_number=self.line_number,
            source_path=self.source_path,
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


class Scope:
    def __init__(self, line_number, deck, config):
        self.start_line_number = line_number
        self.current_line_number = line_number
        self.deck = deck
        self.config = config
        self.indent = None
        self.child_scope = None
        self.trace("Opening")

    def check_child_scope(self, indent, line):
        if self.child_scope:
            if self.child_scope.parse_line(
                self.current_line_number, indent, line
            ):
                return True
            self.child_scope = None
        return False

    def parse_line(self, line_number, indent, line):
        self.current_line_number = line_number
        self.trace(f"parse_line({indent!r}, {line!r})")

        if line.strip("\n\r") == "":
            # Blank line; indent might be wrong entirely so ignore it.
            if self.check_child_scope(indent, line):
                return True
        elif self.indent is None:
            self.indent = indent
        elif len(indent) > len(self.indent):
            if not indent.startswith(self.indent):
                self.line_error("Mismatched indent")

            if self.check_child_scope(indent, line):
                return True

            self.unexpected_indent()
            # Add extra indent back to line.
            line = indent.removeprefix(self.indent) + line
        elif len(indent) < len(self.indent):
            # Smaller indent; end of this scope. Any mismatched indent will be
            # caught in the outer scope.
            self.close()
            return False
        elif self.indent != indent:
            self.line_error("Mismatched indent")
        elif self.child_scope:
            # Indent the same, so close any child scope.
            self.child_scope.close()
            self.child_scope = None

        self.parse_unindented(line)
        return True

    def unexpected_indent(self):
        self.line_error("Unexpected indent")

    def close(self):
        if self.child_scope:
            self.child_scope.close()
            self.child_scope = None
        self.trace("Closing")

    def parse_unindented(self, line):
        if matches := CONFIG_REGEX.fullmatch(line):
            self.parse_config(matches[1], matches[2] or "")
        else:
            self.parse_text(line)

    def parse_config(self, directive, rest):
        if directive == "group":
            if rest.strip():
                self.line_error(
                    "Unexpected value after 'group:': {rest.strip()!r}"
                )
            self.child_scope = GroupScope(self)
        else:
            self.child_scope = ConfigScope(self, directive, rest)

    def parse_text(self, line):
        if line.startswith("#") or line.strip() == "":
            # Comment or blank line; ignore.
            return
        self.child_scope = NoteScope(self, line)

    def trace(self, message):
        LOGGER.trace(
            f"{self.logging_id()} at line {self.current_line_number}: {message}"
        )

    def logging_id(self):
        return self.__class__.__name__

    def scope_error(self, error):
        """Raise a syntax error located at the start of the scope."""
        raise DeckSyntaxError(
            str(error),
            self.deck.source_path,
            self.start_line_number,
        )

    def line_error(self, error):
        """Raise a syntax error located at the current line."""
        raise DeckSyntaxError(
            str(error),
            self.deck.source_path,
            self.current_line_number,
        )


class DeckScope(Scope):
    # Supports notes, config, groups, "title:"
    def __init__(self, deck):
        super().__init__(0, deck, NoteConfig())
        self.indent = ""

    def finish(self):
        """Close out inner scopes and return the finished deck."""
        self.close()
        if self.deck.title is None:
            self.scope_error("Does not contain title")
        self.deck.config = self.config
        return self.deck

    def logging_id(self):
        return f"{self.__class__.__name__}[{self.deck.source_path!r}]"


class SubScope(Scope):
    def __init__(self, parent):
        super().__init__(parent.current_line_number, parent.deck, parent.config)


class GroupScope(SubScope):
    # Supports notes, config, groups
    def __init__(self, parent):
        super().__init__(parent)
        self.config = deepcopy(self.config)

    def parse_config(self, directive, rest):
        if directive == "title":
            self.line_error("Title cannot be set within group")
        super().parse_config(directive, rest)


class NoteScope(SubScope):
    # Supports text, config
    def __init__(self, parent, line):
        self.text = [line]
        super().__init__(parent)
        self.config = deepcopy(self.config)

    def unexpected_indent(self):
        pass

    def close(self):
        super().close()
        self.deck.add_note_spec(
            NoteSpec(
                config=self.config.frozen(),
                source_path=self.deck.source_path,
                line_number=self.start_line_number,
                source="".join(self.text),
            )
        )

    def parse_config(self, directive, rest):
        if directive == "title":
            self.line_error("Title cannot be set within note")
        if directive == "group":
            self.line_error("Group cannot be started within note")
        super().parse_config(directive, rest)

    def parse_text(self, line):
        # Quotes can be used to prevent a line from being a config directive.
        line_chomped = line.rstrip("\n\r")
        if line.startswith('"') and line_chomped.endswith('"'):
            # Stip quotes, but add the newline back:
            line = line_chomped[1:-1] + line[len(line_chomped) :]

        self.text.append(line)

    def logging_id(self):
        return f"{self.__class__.__name__}[{self.text[0]!r}]"


class ConfigScope(SubScope):
    # Supports text
    def __init__(self, parent, directive, rest):
        self.directive = directive
        self.text = [rest]
        super().__init__(parent)

    def unexpected_indent(self):
        pass

    def parse_unindented(self, line):
        # Don’t even look for config directives.
        self.text.append(line)

    def parse_config(self, directive, rest):
        raise RuntimeError(
            "parse_config() should be unreachable in ConfigScope"
        )

    def close(self):
        super().close()
        value = "".join(self.text).strip()
        self.trace(f"Trying to set {value!r}")

        if self.directive == "title":
            # We prevent the ConfigScope from being created with this directive
            # in all scopes except DeckScope.
            if "\n" in value:
                self.scope_error("Title cannot have more than one line")
            self.deck.title = value
            return

        try:
            self.config.set(self.directive, value)
        except ValueError as error:
            self.scope_error(error)

    def logging_id(self):
        return f"{self.__class__.__name__}[{self.directive!r}]"


class DeckParser:
    def __init__(self):
        self.finished_decks = []
        self.scope = None

    def open(self, path):
        """Open a deck file for parsing."""
        self.close()
        self.scope = DeckScope(DeckSpec(path))

    def close(self):
        """Close deck file and mark deck finished."""
        if self.scope:
            self.finished_decks.append(self.scope.finish())
        self.scope = None

    def flush_decks(self):
        finished_decks = self.finished_decks
        self.finished_decks = []
        return finished_decks

    def parse_file(self, file_name: str, file: io.TextIOBase):
        for line_number, line in enumerate(file, start=1):
            self.parse_line(file_name, line_number, line)
            yield from self.flush_decks()

        self.close()
        yield from self.flush_decks()

    def parse_path(self, path):
        with open(path, "r", encoding="utf_8") as file:
            yield from self.parse_file(file.name, file)

    def parse_input(self, input):
        """Takes FileInput as parameter."""
        for line in input:
            self.parse_line(input.filename(), input.filelineno(), line)
            yield from self.flush_decks()

        self.close()
        yield from self.flush_decks()

    def parse_line(self, path, line_number, line):
        if not self.scope or self.scope.deck.source_path != path:
            self.open(path)

        unindented = line.lstrip(" \t")
        indent = line[0 : len(line) - len(unindented)]
        assert self.scope.parse_line(line_number, indent, unindented)
