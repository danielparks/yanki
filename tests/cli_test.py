import html
import inspect
import io
import os
from pathlib import Path
import psutil
import pytest
import re
import shutil
import signal
import threading
import time
import urllib.error
from urllib.request import urlopen


REFERENCE_URL = "file://first.png"
REFERENCE_DECK = f"""
title: Test::Reference deck

{REFERENCE_URL} text
  more: more
"""


@pytest.fixture(scope="session")
def reference_deck_path(tmp_path_factory):
    decks = tmp_path_factory.mktemp("decks")
    shutil.copy("test-decks/good/media/first.png", decks / "first.png")
    path = decks / "reference.deck"
    path.write_text(REFERENCE_DECK, encoding="utf_8")
    return path


def local_tests():
    """Get test names in this file."""
    for name, value in globals().items():
        if inspect.isfunction(value) and name.startswith("test_"):
            yield name


def test_yanki_help(yanki):
    result = yanki.run("--help", print_result=False)
    try:
        assert result.returncode == 0
        assert result.stdout.startswith("Usage: yanki")
        assert result.stderr == ""

        split = result.stdout.split("Commands:")
        assert len(split) == 2, 'Expected exactly one "Commands:" in --help'
    except:
        # We only care about the --help output if it looks malformed
        result.print()
        raise

    # Extract the commands listed in --help
    commands = set()
    for line in split[1].split("\n"):
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        commands.add("test_yanki_" + parts[0].replace("-", "_"))

    assert commands <= set(local_tests()), "Expected a test for every command"


def test_yanki_build(yanki, reference_deck_path):
    result = yanki.run("build", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert reference_deck_path.with_suffix(".apkg").is_file()


# Fake `open` doesn’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_update(yanki, reference_deck_path):
    result = yanki.run("update", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout.endswith(".apkg\n")
    assert Path(result.stdout[:-1]).is_file()
    assert result.stderr == ""


# This doesn’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_serve_http(yanki, reference_deck_path):
    # Need to add result to an object to get it out of thread:
    results = []

    def run_yanki_serve_http():
        results.append(
            yanki.run("serve-http", "--run-seconds", "5", reference_deck_path)
        )

    httpd = threading.Thread(target=run_yanki_serve_http)
    httpd.start()

    start = time.time()
    html = None
    while time.time() - start < 5:  # 5 second timeout
        time.sleep(0.1)
        try:
            html = urlopen("http://localhost:8000/").read()
            break
        except urllib.error.URLError as error:
            if not isinstance(error.reason, ConnectionRefusedError):
                # Not connection refused.
                raise

    for child in psutil.Process().children(recursive=False):
        # KLUDGE: Assume that yanki is the only subprocess.
        os.kill(child.pid, signal.SIGTERM)

    httpd.join()

    assert html.startswith(b"<!DOCTYPE html>\n")

    assert len(results) == 1
    result = results[0]
    assert result.returncode == -signal.SIGTERM
    # FIXME We don’t always get the “Starting HTTP server” on stdout
    assert "GET / HTTP" in result.stderr


def test_yanki_to_html(yanki, reference_deck_path, tmp_path_factory):
    output_path = tmp_path_factory.mktemp("output")
    result = yanki.run("to-html", output_path, reference_deck_path)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""

    index_html = (output_path / "index.html").read_text(encoding="utf_8")
    assert index_html.startswith("<!DOCTYPE html>\n")
    assert index_html.endswith("</html>\n")

    matches = re.search(r'<a href="(deck_[^"]+)"', index_html)
    assert matches is not None
    deck_path = html.unescape(matches.group(1))
    deck_html = (output_path / deck_path).read_text(encoding="utf_8")
    assert deck_html.startswith("<!DOCTYPE html>\n")
    assert deck_html.endswith("</html>\n")
    assert deck_html.count('<div class="note">') == 1


def test_yanki_list_notes(yanki, reference_deck_path):
    result = yanki.run("list-notes", "-f", "{url}", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout == f"{REFERENCE_URL}\n"
    assert result.stderr == ""


def test_yanki_list_final_notes(yanki, reference_deck_path, cache_path):
    """Check that list-notes can list notes after being processed."""
    result = yanki.run("list-notes", "-f", "{media_paths}", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout.startswith(f"{cache_path}/processed_file\\=||")
    assert result.stderr == ""

    # Might as well check CACHEDIR.TAG too. See https://bford.info/cachedir/
    contents = (cache_path / "CACHEDIR.TAG").read_bytes()
    assert contents[:43] == b"Signature: 8a477f597d28d172789f06886806bc55"


# Fake `open` doesn’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_open_videos(yanki, reference_deck_path, cache_path):
    result = yanki.run(
        "open-videos", f"file://{reference_deck_path.parent}/first.png"
    )
    assert result.returncode == 0
    assert result.stdout.startswith(f"{cache_path}/processed_file\\=||")
    assert result.stderr == ""


# input and fake `open` don’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_open_videos_from_file(yanki, reference_deck_path, cache_path):
    result = yanki.run(
        "open-videos-from-file",
        stdin=io.StringIO(f"file://{reference_deck_path.parent}/first.png\n"),
    )
    assert result.returncode == 0
    assert result.stdout.startswith(f"{cache_path}/processed_file\\=||")
    assert result.stderr == ""
