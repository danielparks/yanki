import inspect
from dataclasses import dataclass
from typing import Any


class AsyncCalledFromSyncError(Exception):
    def __init__(self, message="cannot call async method from sync method"):
        super().__init__(message)


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

    async def resolve_async(self, object: object) -> str:
        """Resolve into a string."""
        return self.resolve(object)


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

    async def resolve_async(self, object: object) -> str:
        """Join `self.parts` with `self.join`."""
        return self.join.join(
            [await resolve_async(object, part) for part in self.parts]
        )

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
            method = getattr(object, name)
            if inspect.iscoroutinefunction(method):
                raise AsyncCalledFromSyncError(
                    f"cannot call async method {name} in path "
                    f" {self.method_path} from sync method"
                )
            object = method()
        return str(object)

    async def resolve_async(self, object: object) -> str:
        """Get the value from the method path."""
        for name in self.method_path:
            method = getattr(object, name)
            if inspect.iscoroutinefunction(method):
                object = await method()
            else:
                object = method()
        return str(object)

    def __repr__(self) -> str:
        path = ", ".join([repr(segment) for segment in self.method_path])
        return f"{self.__class__.__name__}({path})"


def resolve(object: object, value: str | Resolvable) -> str:
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


async def resolve_async(object: object, value: str | Resolvable) -> str:
    """Resolve a `str` or a `Resolvable` into a `str`."""
    match value:
        case Resolvable():
            return await value.resolve_async(object)
        case str():
            return value
        case other:
            raise ValueError(f"expected str or Resolvable; got {other!r}")


async def resolve_path_async(
    object: object, path: list[str | Resolvable]
) -> list[str]:
    """Resolve the cache path into strings.

    The cache path can be specified with `Resolvable`s in order to allow
    dynamic paths. For example:

        @cached_json(SelfAttr("id"), "info")

    For each segment of the path, resolve it down to an actual string, e.g.
    `["video_idABCXYZ", "info"]`.
    """
    resolved_path = [await resolve_async(object, segment) for segment in path]
    validate_path(resolved_path)
    return resolved_path


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
