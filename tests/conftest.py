import io
import os
from pathlib import Path
import pytest
from pytest_console_scripts import ScriptRunner, _StrOrPath, RunResult
from typing import Any


@pytest.fixture(scope="session")
def bin_path(tmp_path_factory):
    """bin directory with `open` that just prints its arguments."""
    path = tmp_path_factory.mktemp("bin")

    for command in ["open", "xdg-open"]:
        open_path = path / command
        with open(open_path, "w") as file:
            file.write("#!/bin/sh\necho $*\n")
        open_path.chmod(0o755)

    return path


@pytest.fixture(scope="session")
def cache_path(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


class YankiRunner(ScriptRunner):
    def __init__(
        self,
        launch_mode: str,
        rootdir: Path,
        bin_path: Path,
        cache_path: Path,
        print_result: bool = True,
    ):
        super().__init__(launch_mode, rootdir, print_result)
        self.bin_path = bin_path
        self.cache_path = cache_path

    def __repr__(self) -> str:
        return f"<YankiRunner {self.launch_mode}>"

    def run(
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


@pytest.fixture
def yanki(
    request: pytest.FixtureRequest,
    script_cwd: Path,
    script_launch_mode: str,
    bin_path: Path,
    cache_path: Path,
) -> YankiRunner:
    print_result = not request.config.getoption("--hide-run-results")
    return YankiRunner(
        script_launch_mode, script_cwd, bin_path, cache_path, print_result
    )
