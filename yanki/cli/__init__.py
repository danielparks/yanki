import asyncio
import functools
import json
import logging
import re
import shutil
import sys
import tempfile
import traceback
from multiprocessing import cpu_count
from pathlib import Path

import click
import colorlog
import genanki
import yt_dlp

from yanki.anki import FINAL_NOTE_VARIABLES
from yanki.errors import ExpectedError
from yanki.html_out import write_html
from yanki.parser import NOTE_VARIABLES, find_invalid_format
from yanki.utils import add_trace_logging, find_errors, open_in_app
from yanki.video import BadURLError, FFmpegError, Video, VideoOptions

from .decks import deck_parameters
from .server import server_options

add_trace_logging()
LOGGER = logging.getLogger(__name__)

# Click path value types
WritableDirectoryPath = functools.partial(
    click.Path,
    exists=False,
    dir_okay=True,
    file_okay=False,
    writable=True,
    readable=True,
    executable=True,
)
WritableFilePath = functools.partial(
    click.Path,
    exists=False,
    dir_okay=False,
    file_okay=True,
    writable=True,
)

# Only used to pass debug logging status out to the exception handler.
global_log_debug = False


def main():  # noqa: C901 (complex)
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
        exit_code = 1

        for error in find_errors(group):
            if global_log_debug:
                if error.stdout is not None:
                    sys.stderr.write("STDOUT:\n")
                    sys.stderr.buffer.write(error.stdout)
                    sys.stderr.write("\n")
                sys.stderr.write("STDERR:\n")
                sys.stderr.buffer.write(error.stderr)
                sys.stderr.write("\n")
                traceback.print_exception(error, file=sys.stderr)
            else:
                # FFmpeg errors contain a bytestring of ffmpeg’s output.
                sys.stderr.buffer.write(error.stderr)
                sys.stderr.write(f"\nError in {error.command}. See above.\n")
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
    type=WritableDirectoryPath(path_type=Path),
    help="Path to cache for downloads and media files.",
)
@click.option(
    "--reprocess/--no-reprocess",
    help="Force reprocessing videos.",
)
@click.option(
    "-j",
    "--concurrency",
    default=cpu_count(),
    show_default=True,
    envvar="YANKI_CONCURRENCY",
    show_envvar=True,
    type=click.INT,
    help="Number of ffmpeg process to run at once.",
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
        concurrency=concurrency,
    )

    # Configure logging
    global global_log_debug  # noqa: PLW0603 (global keyword)
    if verbose > 3:
        raise click.UsageError(
            "--verbose or -v may only be specified up to 3 times."
        )
    if verbose == 3:
        global_log_debug = True
        level = logging.TRACE
    elif verbose == 2:
        global_log_debug = True
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)s%(reset)s "
            "%(light_cyan)s%(name)s:%(reset)s %(message)s",
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
@deck_parameters
@click.option(
    "-o",
    "--output",
    type=WritableFilePath(),
    help="Path to save decks to. Defaults to saving indivdual decks to their "
    "own files named after their sources, but with the extension .apkg.",
)
@click.pass_obj
def build(options, decks, output):
    """Build an Anki package from deck files."""
    package = genanki.Package([])  # Only used with --output

    for deck in decks.read_final(options):
        if output is None:
            # Automatically figures out the path to save to.
            deck.save_to_file()
        else:
            deck.save_to_package(package)

    if output:
        package.write_to_file(output)
        LOGGER.info(f"Wrote decks to file {output}")


@cli.command()
@deck_parameters
@click.pass_obj
def update(options, decks):
    """Update Anki from deck files.

    This will build the .apkg file in a temporary directory that will eventually
    be deleted. It will then open the .apkg file with the `open` command.
    """
    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as file:
        file.close()
        package = genanki.Package([])
        for deck in decks.read_final(options):
            deck.save_to_package(package)
        LOGGER.debug(f"Wrote decks to file {file.name}")
        package.write_to_file(file.name)
        LOGGER.debug(f"Opening {file.name}")
        open_in_app([file.name])


class ListNotesCommand(click.Command):
    def format_help_text(self, ctx, formatter):
        super().format_help_text(ctx, formatter)
        formatter.write("\n  Valid format variables:\n")
        for var in sorted(FINAL_NOTE_VARIABLES):
            formatter.write(f"    * {{{var}}}\n")


@cli.command(cls=ListNotesCommand)
@deck_parameters
@click.option(
    "-f",
    "--format",
    default="{url} {clip} {direction} {text}",
    show_default=True,
    type=click.STRING,
    help="The format to output in.",
)
@click.pass_obj
def list_notes(options, decks, format):
    """List notes in deck files."""
    if find_invalid_format(format, NOTE_VARIABLES) is None:
        # Don’t need FinalNotes
        for deck in decks.read_sorted(options):
            for note in deck.notes():
                # FIXME document variables
                print(format.format(**note.variables(deck_id=deck.id())))
    else:
        if error := find_invalid_format(format, FINAL_NOTE_VARIABLES):
            sys.exit(f"Invalid variable in format: {error}")

        for deck in decks.read_final_sorted(options):
            for note in deck.notes():
                # FIXME document variables
                print(format.format(**note.variables()))


@cli.command()
@click.argument("output", type=WritableDirectoryPath(path_type=Path))
@deck_parameters
@click.option(
    "-F",
    "--flashcards/--no-flashcards",
    help="Render notes as flashcards.",
)
@click.pass_obj
def to_html(options, output, decks, flashcards):
    """Generate HTML version of decks."""
    write_html(
        output,
        options.cache_path,
        decks.read_final_sorted(options),
        flashcards=flashcards,
    )


@cli.command()
@deck_parameters
@click.option(
    "-o",
    "--output",
    type=WritableFilePath(allow_dash=True, path_type=Path),
    default="-",
    help="Path to save JSON to, or - to output to stdout.",
)
@click.option(
    "-m",
    "--copy-media-to",
    type=WritableDirectoryPath(),
    default="",
    help="Directory to copy media into (leave blank to not copy media).",
)
@click.option(
    "-p",
    "--html-media-prefix",
    default="",
    help="Prefix for media references in HTML (may be a URL).",
)
@click.pass_obj
def to_json(options, output, decks, copy_media_to, html_media_prefix):
    """Generate JSON version of decks.

    Optionally, copy the media for the decks into a directory.
    """
    decks = [
        deck.to_dict(base_url=html_media_prefix)
        for deck in decks.read_final_sorted(options)
    ]

    if copy_media_to:
        copy_media_to = Path(copy_media_to)
        copy_media_to.mkdir(parents=True, exist_ok=True)
        for deck in decks:
            for note in deck["notes"]:
                new_paths = []
                for source in note["media_paths"]:
                    destination = copy_media_to / Path(source).name
                    LOGGER.info(f"Copying media to {destination}")
                    shutil.copy2(source, destination)
                    destination.chmod(0o644)
                    new_paths.append(str(destination))

                note["media_paths"] = new_paths

    with click.open_file(output, "w", encoding="utf_8") as file:
        LOGGER.info(f"Writing JSON to {output}")
        json.dump(decks, file)


@cli.command()
@deck_parameters
@server_options
@click.option(
    "-F",
    "--flashcards/--no-flashcards",
    help="Render notes as flashcards.",
)
@click.pass_obj
def serve_http(options, decks, server, flashcards):
    """Serve HTML summary of deck on localhost:8000."""
    write_html(
        options.cache_path,
        options.cache_path,
        decks.read_final_sorted(options),
        flashcards=flashcards,
    )

    server.serve_forever(directory=options.cache_path)


@cli.command()
@click.argument("urls", nargs=-1, type=click.STRING)
@click.pass_obj
def open_videos(options, urls):
    """Download, process, and open video URLs."""
    for url in urls:
        video = Video(url, options=options)
        open_in_app([asyncio.run(video.processed_video_async())])


@cli.command()
@click.argument("files", nargs=-1, type=click.File("r", encoding="utf_8"))
@click.pass_obj
def open_videos_from_file(options, files):
    """Download videos listed in a file and open them.

    If you don’t pass any arguments this will read from stdin. Videos will be
    downloaded and minimally processed, then opened with the open command.
    """
    if len(files) == 0:
        files = [sys.stdin]

    for file in files:
        for url in _find_urls(file):
            try:
                video = Video(url, options=options)
                open_in_app([asyncio.run(video.processed_video_async())])
            except BadURLError as error:
                print(f"Error: {error}")
            except yt_dlp.utils.DownloadError:
                # yt_dlp prints the error itself.
                pass


def _find_urls(file):
    """Find URLs in a file to open.

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


if __name__ == "__main__":
    # Needed to call script directly, e.g. for profiling.
    main()
