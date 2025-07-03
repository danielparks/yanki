import asyncio
import fcntl
import functools
import inspect
import io
import json
import logging
import os
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from yanki.utils import add_trace_logging, fs_escape

add_trace_logging()

CACHEDIR_TAG_CONTENT = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by Yanki.
# For information about cache directory tags, see:
#	https://bford.info/cachedir/
#
# For information about yanki, see:
#   https://github.com/danielparks/Yanki
"""

# cache changes
#   * each video in a directory to make it easier to track
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
        self, path: Path | None = None, *, logger: logging.Logger | None = None
    ):
        """Set up the cache directory."""
        self._cachedir_tag_written = False
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
        return self._values.get(tuple(path), _UNSET)

    def set_entry_value(self, path: list[str], value: Any):
        """Save a value to the memory cache for a cache entry path."""
        if value is _UNSET or value is _INVALID:
            self._values.pop(tuple(path), None)
        else:
            self._values[tuple(path)] = value

    def thread_lock(self, path: list[str]) -> threading.Lock:
        with self._lock_lock:
            if path not in self._locks:
                self._locks[path] = threading.Lock()
            elif not isinstance(self._locks[path], threading.Lock):
                raise MixedLockError()
            return self._locks[path]

    def async_lock(self, path: list[str]) -> asyncio.Lock:
        with self._lock_lock:
            if path not in self._locks:
                self._locks[path] = asyncio.Lock()
            elif not isinstance(self._locks[path], asyncio.Lock):
                raise MixedLockError()
            return self._locks[path]

    def ensure_tag(self):
        """Make sure cache/CACHEDIR.TAG exists."""
        if not self._cachedir_tag_written:
            (self.path / "CACHEDIR.TAG").write_text(
                CACHEDIR_TAG_CONTENT, encoding="ascii"
            )
            self._cachedir_tag_written = True


class Resolvable:
    """Abstract base class for something that can be resolved."""

    def resolve(self, _object: Any) -> str:
        """Resolve into a string.

        Takes the object the cached method runs on as a parameter. For example:

            class Video:
                # . . .
                @cached_json(SelfAttr("id"), "info")
                def info(self):
                    # . . .

        In the above example, `SelfAttr("id").resolve(video)` would return
        `video.id` as a string, making the path `["VIDEOID", "info"]`.
        """
        raise NotImplementedError("Resolvable cannot be used directly")


@dataclass
class Join(Resolvable):
    """Join `Resolvable`s into a string."""

    def __init__(self, *parts: list[str | Resolvable], join: str = ""):
        """Join `parts` that can be `Resolvable`s."""
        self.parts = parts
        self.join = join

    def resolve(self, object: object) -> str:
        """Join `self.parts` with `self.join`."""
        return self.join.join([resolve(object, part) for part in self.parts])

    def __repr__(self) -> str:
        parts = ", ".join([repr(part) for part in self.parts])
        return f"{self.__class__.__name__}({parts}, join={self.join!r})"


class SelfAttr(Resolvable):
    """Resolve to the value of an attribute.

    For example:

        class Video:
            # . . .
            @cached_json(SelfAttr("id"), "info")
            def info(self):
                # . . .

    In the above example, `SelfAttr("id").resolve(video)` would return
    `video.id` as a string, making the path `["VIDEOID", "info"]`.
    """

    def __init__(self, *attr_path: str):
        """Store the path to the attribute."""
        self.attr_path = attr_path

    def resolve(self, object: object) -> str:
        """Get the value from the attribute path."""
        for attr in self.attr_path:
            object = getattr(object, attr)
        return str(object)

    def __repr__(self) -> str:
        path = ", ".join([repr(segment) for segment in self.attr_path])
        return f"{self.__class__.__name__}({path})"


class SelfMethod(Resolvable):
    """Resolve to the value returned by a method.

    For example:

        class Video:
            # . . .
            @cached_json(SelfMethod("title"), "info")
            def info(self):
                # . . .

    In the above example, `SelfMethod("title").resolve(video)` would return
    `video.title()` as a string, making the path `["VIDEO TITLE", "info"]`.
    """

    def __init__(self, *method_path: list[str]):
        """Store a path to the method."""
        self.method_path = method_path

    def resolve(self, object: object) -> str:
        """Get the value from the method path."""
        for name in self.method_path:
            object = getattr(object, name)()
        return str(object)

    def __repr__(self) -> str:
        path = ", ".join([repr(segment) for segment in self.method_path])
        return f"{self.__class__.__name__}({path})"


# Sentinel value for Entry.
_UNSET = object()
_INVALID = object()


class LoadInvalidError(Exception):
    def __init__(self, message="loaded invalid value"):
        super().__init__(message)


@dataclass
class Entry:
    object: object
    cache_attr: str
    cache_path: list[str | Resolvable]
    loader: Callable
    _value: Any = _UNSET

    def load(self) -> Any:
        """Run the loader."""
        self._value = self.loader(self.object)
        return self._value

    async def load_async(self) -> Any:
        """Run the loader."""
        self._value = await self.loader(self.object)
        return self._value

    def is_set(self) -> bool:
        """Is the value of this entry set?"""
        return self._value is not _UNSET

    def is_valid(self) -> bool:
        """Is the value of this entry valid?

        Should only by called if the value is set.
        """
        return self._value is not _INVALID

    def needs_load(self) -> bool:
        """Does the loader need to be called?"""
        return not self.is_set() or not self.is_valid()

    @property
    def value(self) -> Any:
        """Get the value from this entry or _UNSET or _INVALID."""
        return self._value

    def read_file(self) -> Any:
        """Read value from `self.file_path`.

        May raise `FileNotFoundError`.
        """
        raise NotImplementedError("abstract base class")

    def write_file(self):
        """Write value to `self.working_path`."""
        raise NotImplementedError("abstract base class")

    def check_memory_cache(self) -> bool:
        """Check if the value is already in memory.

        Returns `True` if `self.value` will return the correct value.
        """
        if not self.needs_load():
            return True
        self._value = self.cache.get_entry_value(self.resolved_cache_path)
        return not self.needs_load()

    def get_value(self) -> Any:
        """Get the value from this entry.

        If this entry is unset or invalid, this will load the value.
        """
        if self.check_memory_cache():
            return self.value

        self.logger.trace("acquiring threading lock")
        with self.cache.thread_lock(tuple(self.resolved_cache_path)):
            try:
                self.logger.trace("acquired threading lock")

                # Another thread might have loaded the value.
                if self.check_memory_cache():
                    return self.value

                with self._lock_and_read_cache() as lock_file:
                    if self.needs_load():
                        result = self._load_and_write(lock_file)
                        if self.needs_load():
                            # The loader elected not to cache; just pass the
                            # return value through.
                            return result
                self.cache.set_entry_value(
                    self.resolved_cache_path, self._value
                )
                return self.value
            finally:
                self.logger.trace("releasing threading lock")

    async def get_value_async(self) -> Any:
        """Get the value from this entry.

        If this entry is unset or invalid, this will load the value.
        """
        if self.check_memory_cache():
            return self.value

        self.logger.trace("acquiring async lock")
        async with self.cache.async_lock(tuple(self.resolved_cache_path)):
            try:
                self.logger.trace("acquired async lock")

                # Another thread might have loaded the value.
                if self.check_memory_cache():
                    return self.value

                with self._lock_and_read_cache() as lock_file:
                    if self.needs_load():
                        result = await self._load_and_write_async(lock_file)
                        if self.needs_load():
                            # The loader elected not to cache; just pass the
                            # return value through.
                            return result
                self.cache.set_entry_value(
                    self.resolved_cache_path, self._value
                )
                return self.value
            finally:
                self.logger.trace("releasing async lock")

    @contextmanager
    def _lock_and_read_cache(self) -> Generator:
        """Gets a shared file lock and reads the file system cache."""
        lock_path = self.file_path.with_name(f"_lock_{self.file_path.name}")
        self.logger.trace(f"opening {lock_path} for reading")
        with lock_path.open("a+", encoding="utf_8") as lock_file:
            lock_file.seek(0)
            self.logger.trace(f"acquiring shared lock on {lock_path}")
            fcntl.lockf(lock_file, fcntl.LOCK_SH)
            self.logger.trace(f"acquired shared lock on {lock_path}")

            self._read_cache(lock_file)

            try:
                yield lock_file
            finally:
                self.logger.trace(f"closing {lock_path} and releasing locks")

    def _read_cache(self, lock_file: io.IOBase):
        assert lock_file.readable(), "reading cache requires read lock"  # noqa: S101 just a sanity check
        try:
            self._value = self.read_file()
        except FileNotFoundError:
            self._value = _UNSET

    def _load_and_write(self, lock_file: io.IOBase) -> Any:
        with self._write_lock(lock_file):
            # It’s possible that another process loaded the value while we were
            # waiting for a write lock.
            self._read_cache(lock_file)
            if not self.needs_load():
                return self.value
            self.logger.trace("calling loader")
            return self._post_load(self.load())

    async def _load_and_write_async(self, lock_file: io.IOBase) -> Any:
        with self._write_lock(lock_file):
            # It’s possible that another process loaded the value while we were
            # waiting for a write lock.
            self._read_cache(lock_file)
            if not self.needs_load():
                return self.value
            self.logger.trace("calling async loader")
            return self._post_load(await self.load_async())

    @contextmanager
    def _write_lock(self, lock_file: io.IOBase) -> Generator:
        self.logger.debug("open for writing")
        self.logger.trace(f"acquiring exclusive lock on {lock_file.name}")
        fcntl.lockf(lock_file, fcntl.LOCK_EX)
        self.logger.trace(f"acquired exclusive lock on {lock_file.name}")
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        self.working_path.unlink(missing_ok=True)

        try:
            yield
        finally:
            self.working_path.unlink(missing_ok=True)
            lock_file.truncate()

    def _post_load(self, load_return: Any) -> Any:
        """Save value set by `load()` or pass through its return.

        This must be called within a write lock.
        """
        if not self.is_set():
            # Don’t cache, just pass through the return.
            self.logger.debug("entry value not set after loading")
            return load_return
        if not self.is_valid():
            raise LoadInvalidError()

        self.write_file()
        self.working_path.rename(self.file_path)
        self.logger.debug(f"saved to {self.file_path}")
        return self.value

    @functools.cached_property
    def cache(self) -> Cache:
        return getattr(self.object, self.cache_attr)

    @functools.cached_property
    def resolved_cache_path(self) -> list[str]:
        return resolve_path(self.object, self.cache_path)

    @functools.cached_property
    def logger(self) -> logging.Logger:
        return self.cache.logger.getChild(
            f"entry.{list(self.resolved_cache_path)}"
        )

    @functools.cached_property
    def file_path(self) -> Path:
        """The actual cache file on the file system."""
        return self.cache.file_path_for_entry(self.resolved_cache_path)

    @functools.cached_property
    def working_path(self) -> Path:
        """The path to which to write.

        The loaded value is written to this path, then moved to the final path
        once the loader finishes. This makes loading data atomic.
        """
        return self.file_path.with_name(f"_working_{self.file_path.name}")


@dataclass
class EntryPath(Entry):
    """A cache entry that is an opaque file.

    The loader will be passed a path. If it writes to that path it will be
    stored in the cache.
    """

    def is_set(self):
        """Is the value of this entry set?"""
        return self.file_path.exists() or self.working_path.exists()

    def is_valid(self):
        """Is the value of this entry valid?

        Should only by called if the value is set.
        """
        return True

    @property
    def value(self) -> Any:
        """Get the value from this entry or _UNSET or _INVALID."""
        if self.is_set():
            return self.file_path
        return _UNSET

    def _read_cache(self, _lock_file: io.IOBase):
        # Nothing to do: is_set() and value() do all the work.
        pass

    def write_file(self):
        # Nothing to do: the loader is responsible for this.
        pass

    def load(self) -> Path:
        """Run the loader."""
        kwargs = {}
        if "final_path" in inspect.signature(self.loader).parameters:
            kwargs["final_path"] = self.file_path
        result = self.loader(self.object, self.working_path, **kwargs)
        if self.needs_load():
            return result
        self._value = result
        return self._value

    async def load_async(self) -> Path:
        """Run the loader."""
        kwargs = {}
        if "final_path" in inspect.signature(self.loader).parameters:
            kwargs["final_path"] = self.file_path
        result = await self.loader(self.object, self.working_path, **kwargs)
        if self.needs_load():
            return result
        self._value = result
        return self._value


@dataclass
class EntryContent(Entry):
    """A cache entry that stores its value in a file."""

    encoding: str | None = "utf_8"

    def read_file(self) -> Any:
        try:
            if self.encoding:
                return self.file_path.read_text(encoding=self.encoding)
            return self.file_path.read_bytes()
        except FileNotFoundError:
            return _UNSET

    def write_file(self):
        if self.encoding:
            return self.working_path.write_text(
                self._value, encoding=self.encoding
            )
        return self.working_path.write_bytes(self._value)


@dataclass
class EntryJson(Entry):
    """A cache entry that stores its value as JSON."""

    # FIXME value(*args) to dig into value

    version: int = 0
    already_logged: bool = False

    def load(self) -> Any:
        """Run the loader."""
        self._value = {
            "value": self.loader(self.object),
            "version": self.version,
        }
        return self._value

    async def load_async(self) -> Any:
        """Run the loader."""
        self._value = {
            "value": await self.loader(self.object),
            "version": self.version,
        }
        return self._value

    def is_set(self):
        """Is the value of this entry set?"""
        return self.value is not _UNSET

    def is_valid(self):
        """Is the value of this entry valid?"""
        return self.value is not _INVALID

    @property
    def value(self) -> Any:
        """Get the value from this entry or _UNSET or _INVALID."""
        if self._value is _UNSET:
            return _UNSET
        try:
            if self._value["version"] != self.version:
                if not self.already_logged:
                    self.logger.debug(
                        f"loaded v{self._value['version']!r}; expected "
                        f"v{self.version!r}; reloading"
                    )
                    self.already_logged = True
                return _INVALID
            return self._value["value"]
        except (TypeError, KeyError):
            return _INVALID

    @functools.cached_property
    def file_path(self):
        """file_path defaults to ending with .json."""
        file_path = super().file_path
        if not file_path.suffix:
            file_path = file_path.with_suffix(".json")
        return file_path

    def read_file(self) -> Any:
        """Read the contents of the file and return the value."""
        with self.file_path.open() as file:
            return json.load(file)

    def write_file(self):
        """Write `self._value` to the the file."""
        with self.working_path.open("w") as file:
            json.dump(
                self._value,
                file,
                sort_keys=True,
            )


def validate_path(path):
    """Validate a cache path.

    This will ignore anything in path that is not a `str`, so it can be called
    before `resolve_path()` to validate just the literal segments.

    This will raise a `ValueError` if it finds a problem.
    """
    if not path:
        raise ValueError("path must have at least one segment")
    # All segment values are valid including "", "..", and "/"; `Cache` will use
    # `fs_escape()` on anything that would cause problems on the file system.


def resolve(object: object, value: str | Resolvable):
    """Resolve a `str` or a `Resolvable` into a `str`."""
    match value:
        case Resolvable():
            return value.resolve(object)
        case str():
            return value
        case other:
            raise ValueError(f"expected str or Resolvable; got {other!r}")


def resolve_path(object: object, path: list[str | Resolvable]) -> list[str]:
    """Resolve the cache path into strings.

    The cache path can be specified with `Resolvable`s in order to allow
    dynamic paths. For example:

        @cached_json(SelfAttr("id"), "info")

    For each segment of the path, resolve it down to an actual string, e.g.
    `["video_idABCXYZ", "info"]`.
    """
    resolved_path = [resolve(object, segment) for segment in path]
    validate_path(resolved_path)
    return resolved_path


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
