import fcntl
import functools
import inspect
import io
import json
import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yanki.utils import add_trace_logging

from .resolvable import Resolvable, resolve_path, resolve_path_async

add_trace_logging()

# Sentinel value for Entry.
UNSET = object()
INVALID = object()


class LoadInvalidError(Exception):
    def __init__(self, message="loaded invalid value"):
        super().__init__(message)


class UnresolvedEntryError(Exception):
    def __init__(
        self,
        message="resolve_cache_path(_async) must be called first",
    ):
        super().__init__(message)


@dataclass
class Entry:
    object: object
    cache_attr: str
    cache_path: list[str | Resolvable]
    loader: Callable
    _value: Any = UNSET
    _resolved_cache_path: list[str] | None = field(init=False, default=None)

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
        return self._value is not UNSET

    def is_valid(self) -> bool:
        """Is the value of this entry valid?

        Should only by called if the value is set.
        """
        return self._value is not INVALID

    def needs_load(self) -> bool:
        """Does the loader need to be called?"""
        return not self.is_set() or not self.is_valid()

    @property
    def value(self) -> Any:
        """Get the value from this entry or UNSET or INVALID."""
        return self._value

    def read_file(self) -> Any:
        """Read value from `self.file_path`.

        May raise `FileNotFoundError`.
        """
        raise NotImplementedError("abstract base class")

    def write_file(self, _lock_file: io.IOBase):
        """Write value to `self.working_path`."""
        raise NotImplementedError("abstract base class")

    def check_memory_cache(self) -> bool:
        """Check if the value is already in memory.

        Returns `True` if `self.value` will return the correct value.
        """
        if not self.needs_load():
            return True
        self._value = self.cache.get_entry_value(self.resolved_cache_path())
        return not self.needs_load()

    def get_value(self, *, reload: bool = False) -> Any:
        """Get the value from this entry.

        If this entry is unset or invalid, this will load the value.
        """
        self.resolve_cache_path()

        if reload:
            self.logger.debug("reloading")

        if not reload and self.check_memory_cache():
            return self.value

        with self.cache.thread_lock(tuple(self.resolved_cache_path())):
            if not reload:
                # Another thread might have loaded the value.
                if self.check_memory_cache():
                    return self.value

                self._read_cache()

            if reload or self.needs_load():
                result = self._load_and_write(reload=reload)
                if self.needs_load():
                    # The loader elected not to cache; just pass the
                    # return value through.
                    return result

            self.cache.set_entry_value(self.resolved_cache_path(), self._value)
            return self.value

    async def get_value_async(self, *, reload: bool = False) -> Any:
        """Get the value from this entry.

        If this entry is unset or invalid, this will load the value.
        """
        await self.resolve_cache_path_async()

        if reload:
            self.logger.debug("reloading")

        if not reload and self.check_memory_cache():
            return self.value

        async with self.cache.async_lock(tuple(self.resolved_cache_path())):
            if not reload:
                # Another thread might have loaded the value.
                if self.check_memory_cache():
                    return self.value

                self._read_cache()

            if reload or self.needs_load():
                result = await self._load_and_write_async(reload=reload)
                if self.needs_load():
                    # The loader elected not to cache; just pass the
                    # return value through.
                    return result

            self.cache.set_entry_value(self.resolved_cache_path(), self._value)
            return self.value

    def _read_cache(self):
        try:
            self._value = self.read_file()
        except FileNotFoundError:
            self._value = UNSET

    def _load_and_write(self, *, reload: bool) -> Any:
        with self._write_lock() as lock_file:
            if not reload:
                # It’s possible that another process loaded the value while we
                # were waiting for a write lock.
                self._read_cache()
                if not self.needs_load():
                    return self.value
            self.logger.trace("calling loader")
            return self._post_load(self.load(), lock_file)

    async def _load_and_write_async(self, *, reload: bool) -> Any:
        with self._write_lock() as lock_file:
            if not reload:
                # It’s possible that another process loaded the value while we
                # were waiting for a write lock.
                self._read_cache()
                if not self.needs_load():
                    return self.value
            self.logger.trace("calling async loader")
            return self._post_load(await self.load_async(), lock_file)

    @contextmanager
    def _write_lock(self) -> Generator:
        lock_path = self.file_path.with_name(f"_lock_{self.file_path.name}")
        self.logger.debug(f"opening {lock_path} for writing")
        with lock_path.open("a+", encoding="utf_8") as lock_file:
            lock_file.seek(0)
            self.logger.trace(f"acquiring exclusive lock on {lock_path}")
            fcntl.lockf(lock_file, fcntl.LOCK_EX)
            self.logger.trace(f"acquired exclusive lock on {lock_path}")
            lock_file.truncate()
            lock_file.write(str(os.getpid()))
            self.working_path.unlink(missing_ok=True)

            try:
                yield lock_file
            finally:
                self.working_path.unlink(missing_ok=True)
                lock_file.truncate()
                self.logger.trace(f"closing {lock_path} and releasing lock")

    def _post_load(self, load_return: Any, lock_file: io.IOBase) -> Any:
        """Save value set by `load()` or pass through its return.

        This must be called within a write lock.
        """
        if not self.is_set():
            # Don’t cache, just pass through the return.
            self.logger.debug("entry value not set after loading")
            return load_return
        if not self.is_valid():
            raise LoadInvalidError()

        self.write_file(lock_file)
        self.working_path.rename(self.file_path)
        self.logger.debug(f"saved to {self.file_path}")
        return self.value

    @functools.cached_property
    def cache(self) -> "Cache":  # noqa: F821 circular dependency
        return getattr(self.object, self.cache_attr)

    def resolve_cache_path(self):
        self._resolved_cache_path = resolve_path(self.object, self.cache_path)

    async def resolve_cache_path_async(self):
        self._resolved_cache_path = await resolve_path_async(
            self.object, self.cache_path
        )

    def resolved_cache_path(self) -> list[str]:
        if self._resolved_cache_path is None:
            raise UnresolvedEntryError()
        return self._resolved_cache_path

    @functools.cached_property
    def logger(self) -> logging.Logger:
        return self.cache.logger.getChild(
            f"entry.{list(self.resolved_cache_path())}"
        )

    @functools.cached_property
    def file_path(self) -> Path:
        """The actual cache file on the file system."""
        return self.cache.file_path_for_entry(self.resolved_cache_path())

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

    def _read_cache(self):
        if self.file_path.exists():
            self._value = self.file_path

    def write_file(self, _lock_file: io.IOBase):
        # Nothing to do: self._post_load() does this.
        pass

    def load(self) -> Path:
        """Run the loader."""
        kwargs = {}
        if "final_path" in inspect.signature(self.loader).parameters:
            kwargs["final_path"] = self.file_path
        result = self.loader(self.object, self.working_path, **kwargs)
        if not self.working_path.exists():
            return result
        self._value = self.file_path
        return self._value

    async def load_async(self) -> Path:
        """Run the loader."""
        kwargs = {}
        if "final_path" in inspect.signature(self.loader).parameters:
            kwargs["final_path"] = self.file_path
        result = await self.loader(self.object, self.working_path, **kwargs)
        if not self.working_path.exists():
            return result
        self._value = self.file_path
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
            return UNSET

    def write_file(self, lock_file: io.IOBase):
        assert lock_file.writable(), "writing cache requires exclusive lock"  # noqa: S101 just a sanity check
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
        return self.value is not UNSET

    def is_valid(self):
        """Is the value of this entry valid?"""
        return self.value is not INVALID

    @property
    def value(self) -> Any:
        """Get the value from this entry or UNSET or INVALID."""
        if self._value is UNSET:
            return UNSET
        try:
            if self._value["version"] != self.version:
                if not self.already_logged:
                    self.logger.debug(
                        f"loaded v{self._value['version']!r}; expected "
                        f"v{self.version!r}; reloading"
                    )
                    self.already_logged = True
                return INVALID
            return self._value["value"]
        except (TypeError, KeyError):
            return INVALID

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

    def write_file(self, lock_file: io.IOBase):
        """Write `self._value` to the the file."""
        assert lock_file.writable(), "writing cache requires exclusive lock"  # noqa: S101 just a sanity check
        with self.working_path.open("w") as file:
            json.dump(
                self._value,
                file,
                sort_keys=True,
            )
