from pathlib import Path

import pytest

from yanki.utils import NotFileURLError, atomic_open, file_url_to_path


def test_atomic_open(tmp_path):
    path = tmp_path / "prefix.suffix"

    with atomic_open(path) as file:
        file.write("First write\n")
    assert path.read_text() == "First write\n"
    assert [path.name for path in tmp_path.iterdir()] == ["prefix.suffix"]

    with atomic_open(path) as file:
        file.write("Second write\n")
    assert path.read_text() == "Second write\n"
    assert [path.name for path in tmp_path.iterdir()] == ["prefix.suffix"]


def test_atomic_open_error(tmp_path):
    path = tmp_path / "prefix.suffix"

    with atomic_open(path) as file:
        file.write("First write\n")
    assert path.read_text() == "First write\n"
    assert [path.name for path in tmp_path.iterdir()] == ["prefix.suffix"]

    with pytest.raises(RuntimeError) as error_info:  # noqa: PT012 SIM117
        # Ignore PT012: we check for the specific `raise`.
        # Ignore SIM117: nested `with`s makes this more clear.
        with atomic_open(path) as file:
            file.write("Second write\n")
            file.close()
            raise RuntimeError("boo")
    assert error_info.match("boo")

    assert path.read_text() == "First write\n"
    assert [path.name for path in tmp_path.iterdir()] == ["prefix.suffix"]


def test_atomic_open_deleted(tmp_path):
    path = tmp_path / "prefix.suffix"

    with pytest.raises(FileNotFoundError) as error_info:  # noqa: PT012 SIM117
        # Ignore PT012: testing context manager.
        # Ignore SIM117: nested `with`s makes this more clear.
        with atomic_open(path) as file:
            Path(file.name).unlink()
            file.write("First write\n")
    assert error_info.match("No such file or directory")

    assert not path.exists()
    assert [path.name for path in tmp_path.iterdir()] == []


def test_file_url_to_path():
    with pytest.raises(NotFileURLError):
        file_url_to_path("foo")
    with pytest.raises(NotFileURLError):
        file_url_to_path("http://example.com/foo")

    assert file_url_to_path("file://a/b/c") == Path("a/b/c")

    base = Path("/BASE")
    assert base / file_url_to_path("file:///a/b/c") == Path("/a/b/c")
    assert base / file_url_to_path("file://./a/b/c") == Path("/BASE/a/b/c")
    assert base / file_url_to_path("file://") == Path("/BASE")
