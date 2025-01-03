import inspect
import io
import pytest
import shutil


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
    with open(path, "w") as file:
        file.write(REFERENCE_DECK)
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


def test_yanki_serve_http(yanki, reference_deck_path):
    result = yanki.run("serve-http", "--run-seconds", "0", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout == "Starting HTTP server on http://localhost:8000/\n"
    assert result.stderr == ""


def test_yanki_to_html(yanki, reference_deck_path):
    result = yanki.run("to-html", reference_deck_path)
    assert result.returncode == 0
    assert result.stderr == ""

    stdout = result.stdout.strip()
    assert stdout.startswith("<!DOCTYPE html>")
    assert stdout.endswith("</html>")


def test_yanki_list_notes(yanki, reference_deck_path):
    result = yanki.run("list-notes", "-f", "{url}", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout == f"{REFERENCE_URL}\n"
    assert result.stderr == ""


def test_yanki_dump_videos(yanki, reference_deck_path, cache_path):
    result = yanki.run("dump-videos", reference_deck_path)
    assert result.returncode == 0
    assert result.stdout.startswith(
        f"title: Test::Reference deck\n{cache_path}"
    )
    assert result.stderr == ""


# Fake `open` doesn’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_open_videos(yanki, reference_deck_path, cache_path):
    result = yanki.run(
        "open-videos", f"file://{reference_deck_path.parent}/first.png"
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.startswith(f"{cache_path}/processed_file:||")


# input and fake `open` don’t work without subprocess.
@pytest.mark.script_launch_mode("subprocess")
def test_yanki_open_videos_from_file(yanki, reference_deck_path, cache_path):
    result = yanki.run(
        "open-videos-from-file",
        stdin=io.StringIO(f"file://{reference_deck_path.parent}/first.png\n"),
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.startswith(f"{cache_path}/processed_file:||")
