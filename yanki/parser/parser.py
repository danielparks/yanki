import io
import logging
import re
from copy import deepcopy
from pathlib import Path

from yanki.errors import DeckSyntaxError
from yanki.parser.config import NoteConfig
from yanki.parser.model import DeckSpec, NoteSpec
from yanki.utils import add_trace_logging

add_trace_logging()
LOGGER = logging.getLogger(__name__)


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


class Parser:
    def __init__(self, line_number, deck, config):
        self.start_line_number = line_number
        self.current_line_number = line_number
        self.deck = deck
        self.config = config
        self.indent = None
        self.child_parser = None
        self.trace("Opening")

    def check_child_parser(self, indent, line):
        if self.child_parser:
            if self.child_parser.parse_line(
                self.current_line_number, indent, line
            ):
                return True
            self.child_parser = None
        return False

    def parse_line(self, line_number, indent, line):
        self.current_line_number = line_number
        self.trace(f"parse_line({indent!r}, {line!r})")

        if line.strip("\n\r") == "":
            # Blank line; indent might be wrong entirely so ignore it.
            if self.check_child_parser(indent, line):
                return True
        elif self.indent is None:
            self.indent = indent
        elif len(indent) > len(self.indent):
            if not indent.startswith(self.indent):
                self.line_error("Mismatched indent")

            if self.check_child_parser(indent, line):
                return True

            self.unexpected_indent()
            # Add extra indent back to line.
            line = indent.removeprefix(self.indent) + line
        elif len(indent) < len(self.indent):
            # Smaller indent; end of this parser. Any mismatched indent will be
            # caught in the outer parser.
            self.close()
            return False
        elif self.indent != indent:
            self.line_error("Mismatched indent")
        elif self.child_parser:
            # Indent the same, so close any child parser.
            self.child_parser.close()
            self.child_parser = None

        self.parse_unindented(line)
        return True

    def unexpected_indent(self):
        self.line_error("Unexpected indent")

    def close(self):
        if self.child_parser:
            self.child_parser.close()
            self.child_parser = None
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
            self.child_parser = GroupParser(self)
        else:
            self.child_parser = ConfigParser(self, directive, rest)

    def parse_text(self, line):
        if line.startswith("#") or line.strip() == "":
            # Comment or blank line; ignore.
            return
        self.child_parser = NoteParser(self, line)

    def trace(self, message):
        LOGGER.trace(
            f"{self.logging_id()} at line {self.current_line_number}: {message}"
        )

    def logging_id(self):
        return self.__class__.__name__

    def parser_error(self, error):
        """Raise a syntax error located at the start of the parser."""
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


class DeckParser(Parser):
    # Supports notes, config, groups, "title:", "version:"
    def __init__(self, deck):
        super().__init__(0, deck, NoteConfig())
        self.indent = ""

    def finish(self):
        """Close out inner parsers and return the finished deck."""
        self.close()
        if self.deck.title is None:
            self.parser_error("Does not contain title")
        self.deck.config = self.config
        return self.deck

    def logging_id(self):
        return f"{self.__class__.__name__}[{self.deck.source_path!r}]"


class SubParser(Parser):
    def __init__(self, parent):
        super().__init__(parent.current_line_number, parent.deck, parent.config)


class GroupParser(SubParser):
    # Supports notes, config, groups
    def __init__(self, parent):
        super().__init__(parent)
        self.config = deepcopy(self.config)

    def parse_config(self, directive, rest):
        if directive == "title":
            self.line_error("Title cannot be set within group")
        if directive == "version":
            self.line_error("Version cannot be set within group")
        super().parse_config(directive, rest)


class NoteParser(SubParser):
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
        if directive == "version":
            self.line_error("Version cannot be set within note")
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


class ConfigParser(SubParser):
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

    def parse_config(self, _directive, _rest):
        raise RuntimeError(
            "parse_config() should be unreachable in ConfigParser"
        )

    def close(self):
        super().close()
        value = "".join(self.text).strip()
        self.trace(f"Trying to set {value!r}")

        if self.directive == "title":
            # We prevent the ConfigParser from being created with this directive
            # in all parsers except DeckParser.
            if "\n" in value:
                self.parser_error("Title cannot have more than one line")
            self.deck.title = value
            return

        if self.directive == "version":
            # We prevent the ConfigParser from being created with this directive
            # in all parsers except DeckParser.
            if value != "1":
                self.parser_error(
                    "This version of yanki only supports version 1 deck files "
                    f"(found {value!r})"
                )
            return

        try:
            self.config.set(self.directive, value)
        except ValueError as error:
            self.parser_error(error)

    def logging_id(self):
        return f"{self.__class__.__name__}[{self.directive!r}]"


class DeckFilesParser:
    def __init__(self):
        self.finished_decks = []
        self.parser = None

    def open(self, path):
        """Open a deck file for parsing."""
        self.close()
        self.parser = DeckParser(DeckSpec(path))

    def close(self):
        """Close deck file and mark deck finished."""
        if self.parser:
            self.finished_decks.append(self.parser.finish())
        self.parser = None

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
        with Path(path).open("r", encoding="utf_8") as file:
            yield from self.parse_file(file.name, file)

    def parse_input(self, input):
        """Parse files from FileInput."""
        for line in input:
            self.parse_line(input.filename(), input.filelineno(), line)
            yield from self.flush_decks()

        self.close()
        yield from self.flush_decks()

    def parse_line(self, path, line_number, line):
        if not self.parser or self.parser.deck.source_path != path:
            self.open(path)

        unindented = line.lstrip(" \t")
        indent = line[0 : len(line) - len(unindented)]
        if not self.parser.parse_line(line_number, indent, unindented):
            # DeckParser always has 0 indent because an indent starts a child
            # parser. If it returns False to indicate it found an outdent, then
            # something went very wrong.
            raise RuntimeError("DeckParser found impossible outdent")
