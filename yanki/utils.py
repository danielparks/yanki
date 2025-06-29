import contextlib
import dataclasses
import inspect
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import types
import typing
from functools import partial, partialmethod
from pathlib import Path
from urllib.parse import urlparse

from yanki.errors import ExpectedError


class NotFileURLError(ValueError):
    """Raised by file_url_to_path() when the parameter is not a file:// URL."""


def add_trace_logging():
    """Add `logging.TRACE` level. Idempotent."""
    try:
        logging.TRACE  # noqa: B018 (not actually useless)
    except AttributeError:
        # From user DerWeh at https://stackoverflow.com/a/55276759/1043949
        logging.TRACE = 5
        logging.addLevelName(logging.TRACE, "TRACE")
        logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
        logging.trace = partial(logging.log, logging.TRACE)


@contextlib.contextmanager
def atomic_open(path: Path, *, encoding="utf_8", permissions=0o644):
    """Open a file for writing and save it atomically.

    This creates a temporary file in the same directory, writes to it, then
    replaces the target file atomically even if it already exists.
    """
    with tempfile.NamedTemporaryFile(
        mode="wb" if encoding is None else "w",
        encoding=encoding,
        dir=path.parent,
        prefix=f"working_{path.stem}",
        suffix=path.suffix,
        delete=True,
        delete_on_close=False,
    ) as temp_file:
        yield temp_file
        Path(temp_file.name).rename(path)
        # Nothing for NamedTemporaryFile to delete.
        path.chmod(permissions)


def chars_in(chars, input):
    """Return chars from `chars` that are in `input`."""
    return [char for char in chars if char in input]


def file_url_to_path(url: str) -> Path:
    """Convert a file:// URL to a Path.

    Raises NotFileURLError if the URL is not a file:// URL.
    """
    parts = urlparse(url)
    if parts.scheme.lower() != "file":
        raise NotFileURLError(url)

    # urlparse doesn’t handle file: very well:
    #
    #   >>> urlparse('file://./media/first.png')
    #   ParseResult(scheme='file', netloc='.', path='/media/first.png', ...)
    return Path(parts.netloc + parts.path)


def file_not_empty(path: Path):
    """Check that `path` is a file and is non-empty."""
    return path.exists() and path.stat().st_size > 0


def file_safe_name(name):
    """Sanitize a deck title into something safe for the file system."""
    return name.replace("/", "--").replace(" ", "_")


def find_errors(group: ExceptionGroup):
    """Get actual exceptions out of nested exception groups."""
    for error in group.exceptions:
        if isinstance(error, ExceptionGroup):
            yield from find_errors(error)
        else:
            yield error


def get_key_path(data, path: list[any]):
    """Dig into `data` following the `path` of keys.

    For example, `get_key_path(data, ["a", "b", 0]) == data["a"]["b"][0]`.
    """
    for key in path:
        data = data[key]
    return data


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


def open_in_app(arguments):
    """Open a file or URL in the appropriate application."""
    # FIXME only works on macOS and Linux; should handle command not found.
    if os.uname().sysname == "Darwin":
        command = "open"
    elif os.uname().sysname == "Linux":
        command = "xdg-open"
    else:
        raise ExpectedError(
            f"Don’t know how to open {arguments!r} on this platform."
        )

    command_line = [command, *arguments]
    result = subprocess.run(
        command_line,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf_8",
    )

    if result.returncode != 0:
        raise ExpectedError(
            f"Error running {shlex.join(command_line)}: {result.stdout}"
        )

    sys.stdout.write(result.stdout)
