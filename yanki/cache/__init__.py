import asyncio
import functools
import inspect
import logging
import threading
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from yanki.utils import add_trace_logging, fs_escape

from .entry import INVALID, UNSET, Entry, EntryJson, EntryPath
from .resolvable import Resolvable, validate_path

add_trace_logging()

CACHEDIR_TAG_CONTENT = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by Yanki.
# For information about cache directory tags, see:
#	https://bford.info/cachedir/
#
# For information about yanki, see:
#   https://github.com/danielparks/Yanki
"""

# Cache TODO
#   * touch files (directories?) after they’re accessed to mark them used
#   * some way of invalidating metadata, etc. when the source changes?


class MixedLockError(Exception):
    """Two locks of different types requested for the same Entry.

    `Cache` can use `asyncio.Lock` or `threading.Lock` for entries, but they are
    incompatible. If you request one type of lock for an entry and then the
    other, this exception will be raised.
    """

    def __init__(self, message="found mixed lock use for Entry in Cache"):
        super().__init__(message)


class Cache:
    """Manage a cache directory."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        async_lock_limit: int = 64,
        logger: logging.Logger | None = None,
    ):
        """Set up the cache directory."""
        self._cachedir_tag_written = False
        self._async_lock_limit = asyncio.Semaphore(async_lock_limit)
        self._lock_lock = threading.Lock()
        self._locks = {}
        self._values = {}

        if path is None:
            self.temporary_directory = TemporaryDirectory()
            self.path = Path(self.temporary_directory.name)
            cache_name = self.path.name
        else:
            self.path = path
            try:
                cache_name = f"~/{path.relative_to(Path.home())}"
            except ValueError:
                cache_name = str(path)

        self.logger = logger
        if not self.logger:
            self.logger = logging.getLogger(f"{__name__}.[{cache_name}]")

    def file_path_for_entry(self, path: list[str]) -> Path:
        """Get the path to the file system cache file for a cache entry path."""
        if not path:
            raise ValueError("path must have at least one segment")

        file_path = self.path.joinpath(
            *[fs_escape(segment) for segment in path]
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_tag()
        return file_path

    def get_entry_value(self, path: list[str]) -> Any:
        """Get a value from the memory cache for a cache entry path."""
        return self._values.get(tuple(path), UNSET)

    def set_entry_value(self, path: list[str], value: Any):
        """Save a value to the memory cache for a cache entry path."""
        if value is UNSET or value is INVALID:
            self._values.pop(tuple(path), None)
        else:
            self._values[tuple(path)] = value

    @contextmanager
    def thread_lock(self, path: list[str]) -> Generator:
        """Open a threading lock for a cache entry path."""
        self.logger.trace(f"acquiring threading lock for {path}")
        with self._get_lock(threading.Lock, path):
            self.logger.trace(f"acquired threading lock for {path}")
            try:
                yield
            finally:
                self.logger.trace(f"releasing threading lock for {path}")

    @asynccontextmanager
    async def async_lock(self, path: list[str]) -> Generator:
        """Open an async lock for a cache entry path."""

        def _remaining():
            try:
                return f" ({self._async_lock_limit._value} remaining)"  # noqa: SLF001  kludge
            except AttributeError:
                return " (could not determine locks remaining)"

        self.logger.trace(f"acquiring async lock for {path}{_remaining()}")
        async with self._async_lock_limit, self._get_lock(asyncio.Lock, path):
            self.logger.trace(f"acquired async lock for {path}{_remaining()}")
            try:
                yield
            finally:
                self.logger.trace(f"releasing async lock for {path}")

    def ensure_tag(self):
        """Make sure cache/CACHEDIR.TAG exists."""
        if not self._cachedir_tag_written:
            (self.path / "CACHEDIR.TAG").write_text(
                CACHEDIR_TAG_CONTENT, encoding="ascii"
            )
            self._cachedir_tag_written = True

    def _get_lock(
        self, type: type[threading.Lock | asyncio.Lock], path: list[str]
    ) -> threading.Lock | asyncio.Lock:
        with self._lock_lock:
            if path not in self._locks:
                self._locks[path] = type()
            elif not isinstance(self._locks[path], type):
                raise MixedLockError()
            return self._locks[path]


def cached(
    *cache_path: str | Resolvable,
    type: type[Entry],
    cache_attr: str = "cache",
    **decorator_kwargs: Any,
):
    """Decorator to cache the results of a method on the file system.

    For example:

        class Video:
            def __init__(self, cache_fs_path):
                self.cache = Cache(cache_fs_path)
            # . . .
            @cached(SelfAttr("id"), "info", type=EntryJson)
            def info(self):
                # . . .
    """

    def decorator(wrappee):
        @functools.wraps(wrappee)
        def wrapper(self, *access_args, **access_kwargs):
            return type(
                object=self,
                cache_attr=cache_attr,
                cache_path=cache_path,
                loader=wrappee,
                **decorator_kwargs,
            ).get_value(*access_args, **access_kwargs)

        @functools.wraps(wrappee)
        async def wrapper_async(self, *access_args, **access_kwargs):
            return await type(
                object=self,
                cache_attr=cache_attr,
                cache_path=cache_path,
                loader=wrappee,
                **decorator_kwargs,
            ).get_value_async(*access_args, **access_kwargs)

        if inspect.iscoroutinefunction(wrappee):
            return wrapper_async
        return wrapper

    # Fail early if we can.
    validate_path(cache_path)

    return decorator


def cached_json(*cache_path: str | Resolvable, **decorator_kwargs: Any):
    """Decorator to cache the results of a method on the file system as JSON.

    For example:

        class Video:
            def __init__(self, cache_fs_path):
                self.cache = Cache(cache_fs_path)
            # . . .
            @cached_json(SelfAttr("id"), "info")
            def info(self):
                # . . .
    """
    return cached(*cache_path, type=EntryJson, **decorator_kwargs)


def cached_path(*cache_path: str | Resolvable, **decorator_kwargs: Any):
    """Decorator to cache a method that saves to the file system.

    For example:

        class Video:
            def __init__(self, cache_fs_path):
                self.cache = Cache(cache_fs_path)
            # . . .
            @cached_path(SelfAttr("id"), "raw")
            def raw_path(self, path):
                # . . .
                with path.open("x") as file:
                    # write to file

    The method can choose not to cache by not writing to the `path`. In that
    case, whatever the method returns will be returned directly to the caller.
    Otherwise, the return value of the method is ignored.
    """
    return cached(*cache_path, type=EntryPath, **decorator_kwargs)
