import pytest
from yanki.utils import atomic_open


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

    with pytest.raises(RuntimeError) as error_info:
        with atomic_open(path) as file:
            file.write("Second write\n")
            file.close()
            raise RuntimeError("boo")
    assert error_info.match("boo")

    assert path.read_text() == "First write\n"
    assert [path.name for path in tmp_path.iterdir()] == ["prefix.suffix"]
