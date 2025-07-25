import logging
from pathlib import Path

import pytest

from yanki.utils import NotFileURLError, file_url_to_path

LOGGER = logging.getLogger(__name__)


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
