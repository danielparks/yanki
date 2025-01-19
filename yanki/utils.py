import contextlib
import dataclasses
from functools import partial, partialmethod
import inspect
import logging
import os
from pathlib import Path
import tempfile
import types
import typing
from urllib.parse import urlparse


def add_trace_logging():
    try:
        logging.TRACE
    except AttributeError:
        # From user DerWeh at https://stackoverflow.com/a/55276759/1043949
        logging.TRACE = 5
        logging.addLevelName(logging.TRACE, "TRACE")
        logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
        logging.trace = partial(logging.log, logging.TRACE)


class NotFileURL(ValueError):
    """Raised by file_url_to_path() when the parameter is not a file:// URL."""

    pass


def file_url_to_path(url: str) -> Path:
    """
    Convert a file:// URL to a Path.

    Raises NotFileURL if the URL is not a file:// URL.
    """
    parts = urlparse(url)
    if parts.scheme.lower() != "file":
        raise NotFileURL(url)

    # urlparse doesn’t handle file: very well:
    #
    #   >>> urlparse('file://./media/first.png')
    #   ParseResult(scheme='file', netloc='.', path='/media/first.png', ...)
    return Path(parts.netloc + parts.path)


def file_not_empty(path):
    """Checks that the path is a file and is non-empty."""
    return os.path.exists(path) and os.stat(path).st_size > 0


@contextlib.contextmanager
def atomic_open(path, encoding="utf_8"):
    """
    Open a file for writing and save it atomically.

    This creates a temporary file in the same directory, writes to it, then
    replaces the target file atomically even if it already exists.
    """

    if encoding is None:
        mode = "wb"
    else:
        mode = "w"

    directory = os.path.dirname(path)
    (prefix, suffix) = os.path.splitext(os.path.basename(path))
    with tempfile.NamedTemporaryFile(
        mode=mode,
        encoding=encoding,
        dir=directory,
        prefix=f"working_{prefix}",
        suffix=suffix,
        delete=True,
        delete_on_close=False,
    ) as temp_file:
        yield temp_file
        os.rename(temp_file.name, path)
        # Nothing for NamedTemporaryFile to delete.


def get_key_path(data, path: list[any]):
    for key in path:
        data = data[key]
    return data


def chars_in(chars, input):
    return [char for char in chars if char in input]


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
