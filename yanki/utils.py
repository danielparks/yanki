import contextlib
import dataclasses
import hashlib
import inspect
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import types
import typing
from functools import partial, partialmethod
from pathlib import Path
from urllib.parse import urlparse

from yanki.errors import ExpectedError

FS_ILLEGAL_CHARS = frozenset('/"[]:')
FS_ILLEGAL_NAMES = frozenset(["", ".", ".."])
FS_VALID_SUFFIX_RE = re.compile(r".(\.[a-z0-9]{1,10})$")


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


def chars_in(chars, input):
    """Return chars from `chars` that are in `input`."""
    return [char for char in chars if char in input]


@contextlib.contextmanager
def create_unique_file(path: Path, **kwargs):
    """Create and open a file ensuring it has a unique name."""
    original_stem = path.stem
    i = 2
    while True:
        try:
            with path.open("x", **kwargs) as file:
                yield file
        except FileExistsError:
            path = path.with_stem(f"{original_stem}_{i}")
            i += 1
        else:
            return


def copy_into(source: Path, directory: Path) -> Path:
    """Copy the file at `source` into `directory/file.name`.

    This will replace existing files. It sets the permissions on destination
    file to `0o644`.

    Retuns a `Path` to the new file.
    """
    destination = directory / source.name
    shutil.copy2(source, destination)
    destination.chmod(0o644)
    return destination


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


def find_errors(group: ExceptionGroup):
    """Get actual exceptions out of nested exception groups."""
    for error in group.exceptions:
        if isinstance(error, ExceptionGroup):
            yield from find_errors(error)
        else:
            yield error


def fs_escape(name: str) -> str:
    """Escape a name for the filesystem.

    This must always produce a unique name — no two inputs to this function may
    ever produce the same result.

    FIXME: This does not handle illegal characters or names on Windows.
    """
    if fs_is_legal_name(name):
        return name
    return fs_hash_name(name)


def fs_hash_name(name: str) -> str:
    """Escape a name for the filesystem with a hash (unconditionally).

    This preserves the extension if it only contains ASCII alphanumeric
    characters and is no longer than 10 characters.
    """
    suffix = ""
    if result := FS_VALID_SUFFIX_RE.search(name):
        suffix = result[1]

    hash = hashlib.blake2b(
        name.encode(encoding="utf_8"),
        digest_size=32,
        usedforsecurity=False,
    ).hexdigest()

    return f"_blake2b_{hash}{suffix}"


def fs_is_legal_name(name: str) -> bool:
    """Is the passed name a legal filename?

    FIXME: This does not handle illegal characters or names on Windows.
    """
    return (
        not name.startswith("_")
        and name not in FS_ILLEGAL_NAMES
        and FS_ILLEGAL_CHARS.isdisjoint(name)
    )


def hardlink_into(source: Path, directory: Path) -> Path:
    """Hard link the file at `source` into `directory/file.name`.

    This will remove existing files that are in the way if they don’t already
    link to the right place.

    Retuns a `Path` to the newly linked file.
    """
    # FIXME use shutil.copy2 if hardlink doesn’t work
    link_path = directory / source.name
    try:
        link_path.hardlink_to(source)
    except FileExistsError:
        if not link_path.samefile(source):
            link_path.unlink()
            link_path.hardlink_to(source)
    return link_path


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


def symlink_into(source: Path, directory: Path) -> Path:
    """Symlink the file at `source` into `directory/file.name`.

    This handles duplicate links, and raises `FileExistsError` with a reasonable
    message if there is a conflict.

    Retuns a `Path` to the new symlink.
    """
    link_path = directory / source.name
    try:
        link_path.symlink_to(source)
    except FileExistsError:
        try:
            destination = link_path.readlink()
        except OSError:
            raise FileExistsError(
                "Found non-symlink {str(link_path)!r}"
            ) from None  # Source error messages are confusing

        if destination != source:
            # Links should always have the same name as the source, so this
            # should never happen.
            raise FileExistsError(
                f"Symlink {str(link_path)!r} points to {str(destination)!r} "
                f"instead of {str(source)!r}"
            ) from None  # Source error message is confusing
    return link_path


URL_UNFRIENDLY_RE = re.compile(r'[\|"\[\]:/ _]+')


def url_friendly_name(name: str):
    """Replace runs of URL-unfriendly characters with "_".

    This is not exhaustive.
    """
    return URL_UNFRIENDLY_RE.sub("_", name)
