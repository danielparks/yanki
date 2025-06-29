import io
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from pytest_console_scripts import RunResult, ScriptRunner, _StrOrPath


@pytest.fixture(scope="session")
def bin_path(tmp_path_factory):
    """Get path to directory containing mock `open`.

    This version of `open` will just print its arguments.
    """
    path = tmp_path_factory.mktemp("bin")

    for command in ["open", "xdg-open"]:
        open_path = path / command
        open_path.write_bytes(b"#!/bin/sh\necho $*\n")
        open_path.chmod(0o755)

    return path


@pytest.fixture(scope="session")
def output_path(tmp_path_factory):
    return tmp_path_factory.mktemp("output")


@pytest.fixture(scope="session")
def cache_path(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(scope="session")
def decks_path(tmp_path_factory):
    return tmp_path_factory.mktemp("decks")


REFERENCE_DECK_1 = """
title: Test::Reference deck
file://first.png text
"""


@pytest.fixture(scope="session")
def deck_1_path(decks_path):
    shutil.copy("test-decks/good/media/first.png", decks_path / "first.png")
    path = decks_path / "reference_1.deck"
    path.write_text(REFERENCE_DECK_1, encoding="utf_8")
    return path


REFERENCE_DECK_2 = """
title: Test::Reference deck::2
file://second.png second text
"""


@pytest.fixture(scope="session")
def deck_2_path(decks_path):
    shutil.copy("test-decks/good/media/second.png", decks_path / "second.png")
    path = decks_path / "reference_2.deck"
    path.write_text(REFERENCE_DECK_2, encoding="utf_8")
    return path


class YankiRunner(ScriptRunner):
    def __init__(
        self,
        launch_mode: str,
        rootdir: Path,
        bin_path: Path,
        cache_path: Path,
        *,
        print_result: bool = True,
    ):
        super().__init__(launch_mode, rootdir, print_result)
        self.bin_path = bin_path
        self.cache_path = cache_path

    def __repr__(self) -> str:
        return f"<YankiRunner {self.launch_mode}>"

    def run(  # noqa: PLR0913 (too many arguments)
        self,
        *arguments: _StrOrPath,
        print_result: bool | None = None,
        shell: bool = False,
        cwd: _StrOrPath | None = None,
        env: dict[str, str] | None = None,
        stdin: io.IOBase | None = None,
        check: bool = False,
        **options: Any,
    ) -> RunResult:
        old_level = logging.getLogger("yanki.parser").level
        try:
            logging.getLogger("yanki.parser").setLevel(logging.INFO)

            if env is None:
                env = {}

            # Make sure our overridden `open` is in $PATH
            if "PATH" in env:
                env["PATH"] = f"{self.bin_path}:{env['PATH']}"
            else:
                env["PATH"] = f"{self.bin_path}:{os.environ['PATH']}"

            return super().run(
                ["yanki", "--cache", self.cache_path, *arguments],
                print_result=print_result,
                shell=shell,
                cwd=cwd,
                env=env,
                stdin=stdin,
                check=check,
                **options,
            )
        finally:
            logging.getLogger("yanki.parser").setLevel(old_level)


@pytest.fixture
def yanki(
    request: pytest.FixtureRequest,
    script_cwd: Path,
    script_launch_mode: str,
    bin_path: Path,
    cache_path: Path,
) -> YankiRunner:
    return YankiRunner(
        script_launch_mode,
        script_cwd,
        bin_path,
        cache_path,
        print_result=not request.config.getoption("--hide-run-results"),
    )
