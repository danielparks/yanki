import asyncio
import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from yanki.cache import Cache, cached, cached_json, cached_path
from yanki.cache.entry import EntryContent
from yanki.cache.resolvable import (
    AsyncCalledFromSyncError,
    Join,
    SelfAttr,
    SelfMethod,
)
from yanki.utils import add_trace_logging, fs_hash_name

add_trace_logging()
logging.getLogger("yanki").setLevel(logging.TRACE)
LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True)
class Base:
    cache: Cache = field(default_factory=Cache)
    counter: int = 0

    def assert_once(self):
        """Assert that the calling method was only called once.

        Can only be used by one method in a class.
        """
        assert self.counter == 0, "method called twice"
        self.counter += 1


def ls_r(path: Path):
    return sorted([str(child.relative_to(path)) for child in path.rglob("*")])


def test_cached_json():
    REFERENCE = {"a": "REFERENCE"}  # noqa: N806 uppercase
    cache = Cache()

    @dataclass
    class Thing(Base):
        value: Any

        @cached_json("a")
        def info(self):
            self.assert_once()
            return self.value

    thing = Thing(value=REFERENCE, cache=cache)
    assert ls_r(thing.cache.path) == []

    assert thing.info() == REFERENCE
    assert ls_r(thing.cache.path) == [
        "CACHEDIR.TAG",
        "_lock_a.json",
        "a.json",
    ]
    assert thing.info() == REFERENCE

    thing = Thing(value="OTHER", cache=cache)
    assert thing.info() == REFERENCE, "did not access cache"
    assert thing.info() == REFERENCE, "did not access cache"


def test_cached_json_reload():
    cache = Cache()

    @dataclass
    class Thing(Base):
        value: Any

        @cached_json("foo")
        def info(self):
            self.assert_once()
            return self.value

    thing = Thing("ONE", cache=cache)
    assert thing.info() == "ONE"
    thing.counter = 0
    thing.value = "TWO"
    assert thing.info() == "ONE"
    assert thing.info(reload=True) == "TWO"

    thing = Thing("THREE", cache=cache)
    assert thing.info() == "TWO"
    thing.counter = 0
    thing.value = "THREE"
    assert thing.info() == "TWO"
    assert thing.info(reload=True) == "THREE"


@pytest.mark.asyncio
async def test_cached_json_reload_async():
    cache = Cache()

    @dataclass
    class Thing(Base):
        value: Any

        @cached_json("foo")
        async def info(self):
            self.assert_once()
            return self.value

    thing = Thing("ONE", cache=cache)
    assert await thing.info() == "ONE"
    thing.counter = 0
    thing.value = "TWO"
    assert await thing.info() == "ONE"
    assert await thing.info(reload=True) == "TWO"

    thing = Thing("THREE", cache=cache)
    assert await thing.info() == "TWO"
    thing.counter = 0
    thing.value = "THREE"
    assert await thing.info() == "TWO"
    assert await thing.info(reload=True) == "THREE"


def test_cached_json_version():
    REFERENCE1 = {"a": "REFERENCE_a"}  # noqa: N806 uppercase
    REFERENCE2 = {"b": "REFERENCE_b"}  # noqa: N806 uppercase
    cache = Cache()

    @dataclass
    class Thing1(Base):
        value: Any

        @cached_json("foo", version=1)
        def info(self):
            self.assert_once()
            return self.value

    @dataclass
    class Thing2(Base):
        value: object

        @cached_json("foo", version=2)
        def info(self):
            self.assert_once()
            return self.value

    thing = Thing1(REFERENCE1, cache=cache)
    assert thing.info() == REFERENCE1
    assert thing.info() == REFERENCE1

    thing = Thing1("OTHER", cache=cache)
    assert thing.info() == REFERENCE1, "did not access cache"
    assert thing.info() == REFERENCE1, "did not access cache"

    thing = Thing2(REFERENCE2, cache=cache)
    assert thing.info() == REFERENCE2
    assert thing.info() == REFERENCE2

    thing = Thing2("OTHER2", cache=cache)
    assert thing.info() == REFERENCE2, "did not access cache"
    assert thing.info() == REFERENCE2, "did not access cache"


def test_cached_path():
    cache = Cache()

    @dataclass
    class Thing(Base):
        id: str

        @cached_path("abc")
        def path(self, path):
            self.assert_once()
            path.write_text(self.id)

    thing = Thing(id="test_cached_path", cache=cache)
    assert ls_r(thing.cache.path) == []

    thing_path = thing.path()
    assert thing.cache.path in thing_path.parents
    assert thing_path.read_text() == "test_cached_path"
    assert ls_r(thing.cache.path) == [
        "CACHEDIR.TAG",
        "_lock_abc",
        "abc",
    ]
    assert thing.path() == thing_path

    thing = Thing(id="OTHER", cache=cache)
    assert thing.path() == thing_path
    assert thing_path.read_text() == "test_cached_path"
    assert thing.path() == thing_path


def test_cached_path_reload():
    cache = Cache()

    @dataclass
    class Thing(Base):
        id: str

        @cached_path("abc")
        def path(self, path):
            self.assert_once()
            path.write_text(self.id)

    thing = Thing(id="one", cache=cache)
    assert ls_r(thing.cache.path) == []

    thing_path = thing.path()
    assert thing.cache.path in thing_path.parents
    assert thing_path.read_text() == "one"

    thing.id = "two"
    thing.counter = 0
    assert thing.path() == thing_path
    assert thing.path(reload=True) == thing_path
    assert thing_path.read_text() == "two"
    assert thing.path() == thing_path

    thing = Thing(id="three", cache=cache)
    assert thing.path() == thing_path
    assert thing_path.read_text() == "two"
    assert thing.path(reload=True) == thing_path
    assert thing_path.read_text() == "three"


@pytest.mark.asyncio
async def test_cached_path_reload_async():
    cache = Cache()

    @dataclass
    class Thing(Base):
        id: str

        @cached_path("abc")
        async def path(self, path):
            self.assert_once()
            path.write_text(self.id)

    thing = Thing(id="one", cache=cache)
    assert ls_r(thing.cache.path) == []

    thing_path = await thing.path()
    assert thing.cache.path in thing_path.parents
    assert thing_path.read_text() == "one"

    thing.id = "two"
    thing.counter = 0
    assert await thing.path() == thing_path
    assert await thing.path(reload=True) == thing_path
    assert thing_path.read_text() == "two"
    assert await thing.path() == thing_path

    thing = Thing(id="three", cache=cache)
    assert await thing.path() == thing_path
    assert thing_path.read_text() == "two"
    assert await thing.path(reload=True) == thing_path
    assert thing_path.read_text() == "three"


def test_uncached_path():
    class Thing(Base):
        @cached_path("abc")
        def value(self, _path):
            return "RETURN"

    thing = Thing()
    assert ls_r(thing.cache.path) == []

    assert thing.value() == "RETURN"
    assert ls_r(thing.cache.path) == ["CACHEDIR.TAG", "_lock_abc"]
    assert thing.value() == "RETURN"


@pytest.mark.asyncio
async def test_uncached_path_async():
    class Thing(Base):
        @cached_path("abc")
        async def value(self, _path):
            return "RETURN"

    thing = Thing()
    assert ls_r(thing.cache.path) == []

    assert await thing.value() == "RETURN"
    assert ls_r(thing.cache.path) == ["CACHEDIR.TAG", "_lock_abc"]
    assert await thing.value() == "RETURN"


def test_cached_path_passes_final_path():
    class Thing(Base):
        @cached_path("abc")
        def path(self, working_path, *, final_path):
            assert working_path != final_path
            working_path.write_text(final_path.name)

    assert Thing().path().read_text() == "abc"


CONTENTS_AS_JSON = '{"value": "CONTENTS", "version": 0}'


def test_json_with_path_extension():
    class Thing(Base):
        @cached_json("a.txt")
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert ls_r(thing.cache.path) == [
        "CACHEDIR.TAG",
        "_lock_a.txt",
        "a.txt",
    ]
    assert (thing.cache.path / "a.txt").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_path_len_2():
    class Thing(Base):
        @cached_json("a", "b")
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "a/b.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_path_len_3():
    class Thing(Base):
        @cached_json("a", "b", "c")
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "a/b/c.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_join():
    class Thing(Base):
        @cached_json(Join("a", "b", "c"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "abc.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_join_dot():
    class Thing(Base):
        @cached_json(Join("a", "b", "c", join="_"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "a_b_c.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_join_self_attr():
    @dataclass
    class Thing(Base):
        a: str

        @cached_json(Join("prefix_", SelfAttr("a"), ".txt"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing("VALUE")
    assert thing.info() == "CONTENTS"
    assert (
        thing.cache.path / "prefix_VALUE.txt"
    ).read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_attr_1():
    @dataclass
    class Thing(Base):
        a: str

        @cached_json(SelfAttr("a"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing("VALUE")
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_attr_2():
    @dataclass
    class Wrapper1:
        b: str

    @dataclass
    class Thing(Base):
        a: Wrapper1

        @cached_json(SelfAttr("a", "b"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing(Wrapper1("VALUE"))
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_attr_3():
    @dataclass
    class Wrapper2:
        c: str

    @dataclass
    class Wrapper1:
        b: Wrapper2

    @dataclass
    class Thing(Base):
        a: Wrapper1

        @cached_json(SelfAttr("a", "b", "c"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing(Wrapper1(Wrapper2("VALUE")))
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_method_1():
    class Thing(Base):
        def a(self):
            return "VALUE"

        @cached_json(SelfMethod("a"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_method_2():
    class Wrapper1:
        def b(self):
            return "VALUE"

    class Thing(Base):
        def a(self):
            return Wrapper1()

        @cached_json(SelfMethod("a", "b"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_method_3():
    class Wrapper2:
        def c(self):
            return "VALUE"

    class Wrapper1:
        def b(self):
            return Wrapper2()

    class Thing(Base):
        def a(self):
            return Wrapper1()

        @cached_json(SelfMethod("a", "b", "c"))
        def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert thing.info() == "CONTENTS"


def test_self_method_async_from_sync():
    class Thing(Base):
        async def a(self):
            raise RuntimeError("should not reach here")

        @cached_json(SelfMethod("a"))
        def info(self):
            raise RuntimeError("should not reach here")

    thing = Thing()
    with pytest.raises(AsyncCalledFromSyncError):
        thing.info()


@pytest.mark.asyncio
async def test_self_method_1_async():
    class Thing(Base):
        async def a(self):
            return "VALUE"

        @cached_json(SelfMethod("a"))
        async def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert await thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert await thing.info() == "CONTENTS"


@pytest.mark.asyncio
async def test_self_method_2_async():
    class Wrapper1:
        async def b(self):
            return "VALUE"

    class Thing(Base):
        def a(self):
            return Wrapper1()

        @cached_json(SelfMethod("a", "b"))
        async def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert await thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert await thing.info() == "CONTENTS"


@pytest.mark.asyncio
async def test_self_method_3_async():
    class Wrapper2:
        async def c(self):
            return "VALUE"

    class Wrapper1:
        def b(self):
            return Wrapper2()

    class Thing(Base):
        async def a(self):
            return Wrapper1()

        @cached_json(SelfMethod("a", "b", "c"))
        async def info(self):
            self.assert_once()
            return "CONTENTS"

    thing = Thing()
    assert await thing.info() == "CONTENTS"
    assert (thing.cache.path / "VALUE.json").read_text() == CONTENTS_AS_JSON
    assert await thing.info() == "CONTENTS"


def test_cached_path_empty():
    with pytest.raises(ValueError) as error_info:

        class Thing(Base):
            @cached_path()
            def empty_path(self, _path):
                raise RuntimeError("should not reach here")

    assert error_info.match("path must have at least one segment")


def test_cached_path_invalid_character():
    class Thing(Base):
        @cached_path("a/b")
        def path(self, path):
            self.assert_once()
            path.write_text("CONTENTS")

    hashed_name = fs_hash_name("a/b")
    assert hashed_name.startswith("_")
    thing = Thing()
    assert thing.path().read_text() == "CONTENTS"
    assert thing.path() == thing.cache.path / hashed_name


def test_cached_path_invalid_name():
    class Thing(Base):
        @cached_path("")
        def path(self, path):
            self.assert_once()
            path.write_text("CONTENTS")

    hashed_name = fs_hash_name("")
    assert hashed_name.startswith("_")
    thing = Thing()
    assert thing.path().read_text() == "CONTENTS"
    assert thing.path() == thing.cache.path / hashed_name


@pytest.mark.asyncio
async def test_sync_cache_in_async():
    TASK_COUNT = 20  # noqa: N806 local constant
    cache = Cache()

    @dataclass
    class Thing(Base):
        id: str

        @cached("abc", type=EntryContent)
        def value(self):
            self.assert_once()
            LOGGER.info(f"Fn {id} running")
            return self.id

    async def fn(id: str):
        thing = Thing(id=id, cache=cache)
        await asyncio.sleep(random.uniform(0, 0.1))  # noqa: S311 not cryptography
        return thing.value()

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(fn(f"fn{i}")) for i in range(TASK_COUNT)]

    counts = Counter([task.result() for task in tasks])
    LOGGER.info(f"results: {counts!r}")
    assert len(tasks) == TASK_COUNT
    assert len(counts) == 1
    assert isinstance(next(iter(counts)), str)


@pytest.mark.asyncio
async def test_async_cache_in_async():
    TASK_COUNT = 20  # noqa: N806 local constant
    cache = Cache()

    @dataclass
    class Thing(Base):
        id: str

        @cached("abc", type=EntryContent)
        async def value(self):
            self.assert_once()
            sleep = random.uniform(0, 0.1)  # noqa: S311 not cryptography
            LOGGER.info(f"Fn {id} running (sleep {round(sleep * 1000)} ms)")
            await asyncio.sleep(sleep)
            return self.id

    async def fn(id: str):
        thing = Thing(id=id, cache=cache)
        await asyncio.sleep(random.uniform(0, 0.1))  # noqa: S311 not cryptography
        return await thing.value()

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(fn(f"fn{i}")) for i in range(TASK_COUNT)]

    counts = Counter([task.result() for task in tasks])
    LOGGER.info(f"results: {counts!r}")
    assert len(tasks) == TASK_COUNT
    assert len(counts) == 1
    assert isinstance(next(iter(counts)), str)
