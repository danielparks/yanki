import click
import asyncio
from collections import defaultdict
import colorlog
import functools
import genanki
from http import server
import logging
from multiprocessing import cpu_count
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import traceback
import time
import yt_dlp


from yanki.errors import ExpectedError
from yanki.filter import (
    filter_options,
    read_decks_sorted,
    read_final_decks,
    read_final_decks_sorted,
)
from yanki.html_out import htmlize_deck, generate_index_html, ensure_static_link
from yanki.parser import find_invalid_format, NOTE_VARIABLES
from yanki.anki import FINAL_NOTE_VARIABLES
from yanki.video import Video, BadURL, FFmpegError, VideoOptions
from yanki.utils import add_trace_logging, file_safe_name

add_trace_logging()
LOGGER = logging.getLogger(__name__)


# Only used to pass debug logging status out to the exception handler.
global log_debug
log_debug = False


def main():
    exit_code = 0
    try:
        cli.main(standalone_mode=False)
    except* click.Abort:
        sys.exit("Abort!")
    except* KeyboardInterrupt:
        sys.exit(130)
    except* click.ClickException as group:
        exit_code = 1
        for error in find_errors(group):
            error.show()
            exit_code = error.exit_code
    except* FFmpegError as group:
        global log_debug
        exit_code = 1

        for error in find_errors(group):
            if log_debug:
                sys.stderr.buffer.write(error.stderr)
                sys.stderr.write("\n")
                traceback.print_exception(error, file=sys.stderr)
            else:
                # FFmpeg errors contain a bytestring of ffmpeg’s output.
                sys.stderr.buffer.write(error.stderr)
                print("\nError in ffmpeg. See above.", file=sys.stderr)
    except* ExpectedError as group:
        exit_code = 1
        for error in find_errors(group):
            print(error, file=sys.stderr)

    return exit_code


@click.group()
@click.option("-v", "--verbose", count=True)
@click.option(
    "--cache",
    default=Path("~/.cache/yanki/").expanduser(),
    show_default=True,
    envvar="YANKI_CACHE",
    show_envvar=True,
    type=click.Path(
        exists=False,
        file_okay=False,
        writable=True,
        readable=True,
        executable=True,
        path_type=Path,
    ),
    help="Path to cache for downloads and media files.",
)
@click.option(
    "--reprocess/--no-reprocess",
    help="Reprocess videos whether or not anything has changed.",
)
@click.option(
    "-j",
    "--concurrency",
    default=cpu_count(),
    show_default=True,
    envvar="YANKI_CONCURRENCY",
    show_envvar=True,
    type=click.INT,
    help="How many parallel runs of ffmpeg to allow at once.",
)
@click.pass_context
def cli(ctx, verbose, cache, reprocess, concurrency):
    """Build Anki decks from text files containing YouTube URLs."""

    if concurrency < 1:
        raise click.UsageError("--concurrency must be >= 1.")

    ensure_cache(cache)

    ctx.obj = VideoOptions(
        cache_path=cache,
        progress=verbose > 0,
        reprocess=reprocess,
        semaphore=asyncio.Semaphore(concurrency),
    )

    # Configure logging
    global log_debug
    if verbose > 3:
        raise click.UsageError(
            "--verbose or -v may only be specified up to 3 times."
        )
    elif verbose == 3:
        log_debug = True
        level = logging.TRACE
    elif verbose == 2:
        log_debug = True
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARN

    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)s%(reset)s %(light_cyan)s%(name)s:%(reset)s %(message)s",
            log_colors={
                "TRACE": "bold_purple",
                "DEBUG": "bold_white",
                "INFO": "bold_green",
                "WARNING": "bold_yellow",
                "ERROR": "bold_red",
                "CRITICAL": "bold_red",
            },
        )
    )

    logging.basicConfig(level=level, handlers=[handler])


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
@filter_options
@click.option(
    "-o",
    "--output",
    type=click.Path(exists=False, dir_okay=False, writable=True),
    help="Path to save decks to. Defaults to saving indivdual decks to their "
    "own files named after their sources, but with the extension .apkg.",
)
@click.pass_obj
def build(options, decks, filter, output):
    """Build an Anki package from deck files."""
    package = genanki.Package([])  # Only used with --output

    for deck in read_final_decks(decks, options, filter):
        if output is None:
            # Automatically figures out the path to save to.
            deck.save_to_file()
        else:
            deck.save_to_package(package)

    if output:
        package.write_to_file(output)
        LOGGER.info(f"Wrote decks to file {output}")


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
@filter_options
@click.pass_obj
def update(options, decks, filter):
    """
    Update Anki with one or more decks.

    This will build the .apkg file in a temporary directory that will eventually
    be deleted. It will then open the .apkg file with the `open` command.
    """
    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as file:
        file.close()
        package = genanki.Package([])
        for deck in read_final_decks(decks, options, filter):
            deck.save_to_package(package)
        LOGGER.debug(f"Wrote decks to file {file.name}")
        package.write_to_file(file.name)
        LOGGER.debug(f"Opening {file.name}")
        open_in_app([file.name])


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
@filter_options
@click.option(
    "-f",
    "--format",
    default="{url} {clip} {direction} {text}",
    show_default=True,
    type=click.STRING,
    help="The format to output in.",
)
@click.pass_obj
def list_notes(options, decks, format, filter):
    """Print information about every note in the passed format."""
    if find_invalid_format(format, NOTE_VARIABLES) is None:
        # Don’t need FinalNotes
        for deck in read_decks_sorted(decks, options, filter):
            for note in deck.notes():
                ### FIXME document variables
                print(format.format(**note.variables(deck_id=deck.id())))
    else:
        if error := find_invalid_format(format, FINAL_NOTE_VARIABLES):
            sys.exit(f"Invalid variable in format: {error}")

        for deck in read_final_decks_sorted(decks, options, filter):
            for note in deck.notes():
                ### FIXME document variables
                print(format.format(**note.variables()))


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
@filter_options
@click.option(
    "-F",
    "--flash-cards/--no-flash-cards",
    help="Render notes as flash cards.",
)
@click.pass_obj
def to_html(options, decks, filter, flash_cards):
    """Display decks as HTML on stdout."""
    for deck in read_final_decks_sorted(decks, options, filter):
        print(
            htmlize_deck(
                deck, path_prefix=options.cache_path, flash_cards=flash_cards
            )
        )


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="utf_8"))
@filter_options
@click.option(
    "-F",
    "--flash-cards/--no-flash-cards",
    help="Render notes as flash cards.",
)
@click.option(
    "-o",
    "--open/--no-open",
    "do_open",
    help="Open the web site with `open` after starting the server.",
)
@click.option(
    "-b",
    "--bind",
    default="localhost:8000",
    show_default=True,
    type=click.STRING,
    help="The address and porrt to bind to. NOTE: this is not appropriate for"
    " serving production loads.",
)
@click.option(
    "--run-seconds",
    type=click.FLOAT,
    help="How many seconds to run the server for. May be decimal. If not"
    " specified, the server will run until killed by a signal.",
)
@click.pass_obj
def serve_http(options, decks, filter, flash_cards, do_open, bind, run_seconds):
    """Serve HTML summary of deck on localhost:8000."""
    bind_parts = bind.split(":")
    if len(bind_parts) != 2:
        raise click.UsageError("--bind expects a value in address:port format.")
    [address, port] = bind_parts

    try:
        port = int(port)
    except ValueError:
        raise click.UsageError("--bind expects an integer port.")

    deck_links = []
    html_written = set()
    for deck in read_final_decks_sorted(decks, options, filter):
        file_name = "deck_" + file_safe_name(deck.title) + ".html"
        html_path = options.cache_path / file_name
        if html_path in html_written:
            raise KeyError(
                f"Duplicate path after munging deck title: {html_path}"
            )
        else:
            html_written.add(html_path)

        html_path.write_text(
            htmlize_deck(deck, path_prefix="", flash_cards=flash_cards),
            encoding="utf_8",
        )

        deck_links.append((file_name, deck))

    # FIXME serve html from memory so that you can run multiple copies of
    # this tool at once.
    index_path = options.cache_path / "index.html"
    index_path.write_text(generate_index_html(deck_links), encoding="utf_8")

    indices = defaultdict(list)
    for file_name, deck in deck_links:
        title = deck.title.split("::")
        for i in range(1, len(title) + 1):
            partial = "::".join(title[:i])
            indices[partial].append((file_name, deck))

    for partial, deck_links in indices.items():
        file_name = "index_" + file_safe_name(partial) + ".html"
        index_path = options.cache_path / file_name
        index_path.write_text(
            generate_index_html(deck_links, partial), encoding="utf_8"
        )

    # FIXME it would be great to just serve this directory as /static without
    # needing the symlink.
    ensure_static_link(options.cache_path)

    Handler = functools.partial(
        server.SimpleHTTPRequestHandler, directory=options.cache_path
    )
    httpd = server.HTTPServer((address, port), Handler)

    print(f"Starting HTTP server on http://{bind}/")
    threading.Thread(target=httpd.serve_forever).start()
    start = time.time()

    if do_open:
        time.sleep(0.5)
        open_in_app([f"http://localhost:{port}/"])

    if run_seconds is not None:
        # --open forces the minimum run_seconds to be 0.5.
        run_seconds -= time.time() - start
        if run_seconds > 0:
            time.sleep(run_seconds)

        # httpd.shutdown() hangs if start() hasn’t been called.
        shutdown = threading.Thread(target=httpd.shutdown)
        shutdown.start()

        # Wait for shutdown to take
        for _ in range(10):
            time.sleep(0.1)
            if not shutdown.is_alive():
                return

        print("httpd.shutdown() took more than 1 second; terminating.")
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.1)
        os.kill(os.getpid(), signal.SIGKILL)


@cli.command()
@click.argument("urls", nargs=-1, type=click.STRING)
@click.pass_obj
def open_videos(options, urls):
    """Download and process the video URLs, then open them with `open`."""
    for url in urls:
        video = Video(url, options=options)
        open_in_app([video.processed_video()])


@cli.command()
@click.argument("files", nargs=-1, type=click.File("r", encoding="utf_8"))
@click.pass_obj
def open_videos_from_file(options, files):
    """
    Read files containing video URLs from the arguments or stdin, download the
    videos, process them, and pass them to the `open` command.

    You may use this without arguments if you want to enter the URLs and have
    them opened after each line.
    """
    if len(files) == 0:
        files = [sys.stdin]

    for file in files:
        for url in _find_urls(file):
            try:
                video = Video(url, options=options)
                open_in_app([video.processed_video()])
            except BadURL as error:
                print(f"Error: {error}")
            except yt_dlp.utils.DownloadError:
                # yt_dlp prints the error itself.
                pass


def _find_urls(file):
    """
    Find URLs in a file to open.

    Ignore blank lines and # comments. URLs are separated by whitespace.
    """
    for line in file:
        line = line.strip()
        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue
        # Remove trailing comments
        line = re.split(r"\s+#", line, maxsplit=1)[0]
        for url in line.split():
            if ":" in url:
                yield url
            else:
                print(f"Does not look like a URL: {url!r}")


CACHEDIR_TAG_CONTENT = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by yanki.
# For information about cache directory tags, see:
#	https://bford.info/cachedir/
#
# For information about yanki, see:
#   https://github.com/danielparks/yanki
"""


def ensure_cache(cache_path: Path):
    """Make sure cache is set up."""
    cache_path.mkdir(parents=True, exist_ok=True)

    tag_path = cache_path / "CACHEDIR.TAG"
    tag_path.write_text(CACHEDIR_TAG_CONTENT, encoding="ascii")


def find_errors(group: ExceptionGroup):
    """Get actual exceptions out of nested exception groups."""
    for error in group.exceptions:
        if isinstance(error, ExceptionGroup):
            yield from find_errors(error)
        else:
            yield error


def open_in_app(arguments):
    # FIXME only works on macOS and Linux; should handle command not found.
    if os.uname().sysname == "Darwin":
        command = "open"
    elif os.uname().sysname == "Linux":
        command = "xdg-open"
    else:
        raise ExpectedError(
            f"Don’t know how to open {arguments!r} on this platform."
        )

    command_line = [command, *arguments]
    result = subprocess.run(
        command_line,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf_8",
    )

    if result.returncode != 0:
        raise ExpectedError(
            f"Error running {shlex.join(command_line)}: {result.stdout}"
        )

    sys.stdout.write(result.stdout)


if __name__ == "__main__":
    # Needed to call script directly, e.g. for profiling.
    main()
