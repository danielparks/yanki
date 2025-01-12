import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse
import contextlib


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
