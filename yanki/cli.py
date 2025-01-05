import click
import colorlog
from dataclasses import dataclass
import ffmpeg
import functools
import genanki
import html
from http import server
import logging
import os
from pathlib import PosixPath
import signal
import subprocess
import sys
import textwrap
import threading
import time
import yt_dlp


from yanki.parser import DeckParser, DeckSyntaxError
from yanki.anki import Deck
from yanki.video import Video, BadURL

LOGGER = logging.getLogger(__name__)


@dataclass
class GlobalOptions:
    cache_path: str
    reprocess: bool


# Only used to pass debug logging status out to the exception handler.
global log_debug
log_debug = False


def main():
    try:
        cli.main(standalone_mode=False)
    except click.Abort:
        sys.exit("Abort!")
    except click.ClickException as error:
        error.show()
        return error.exit_code
    except ffmpeg.Error as error:
        global log_debug
        if log_debug:
            sys.stderr.buffer.write(error.stderr)
            sys.stderr.write("\n")
            raise
        else:
            # FFmpeg errors contain a bytestring of ffmpeg’s output.
            sys.stderr.buffer.write(error.stderr)
            sys.exit("\nError in ffmpeg. See above.")
    except BadURL as error:
        sys.exit(error)
    except DeckSyntaxError as error:
        sys.exit(error)
    except KeyboardInterrupt:
        return 130


@click.group()
@click.option("-v", "--verbose", count=True)
@click.option(
    "--cache",
    default=PosixPath("~/.cache/yanki/").expanduser(),
    show_default=True,
    envvar="YANKI_CACHE",
    show_envvar=True,
    type=click.Path(
        exists=False,
        file_okay=False,
        writable=True,
        readable=True,
        executable=True,
    ),
    help="Path to cache for downloads and media files.",
)
@click.option(
    "--reprocess/--no-reprocess",
    help="Reprocess videos whether or not anything has changed.",
)
@click.pass_context
def cli(ctx, verbose, cache, reprocess):
    """Build Anki decks from text files containing YouTube URLs."""
    ctx.obj = GlobalOptions(cache_path=cache, reprocess=reprocess)

    os.makedirs(cache, exist_ok=True)

    # Configure logging
    if verbose > 2:
        raise click.UsageError(
            "--verbose or -v may only be specified up to 2 times."
        )
    elif verbose == 2:
        global log_debug
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
@click.argument("decks", nargs=-1, type=click.File("r", encoding="UTF-8"))
@click.option(
    "-o",
    "--output",
    type=click.Path(exists=False, dir_okay=False, writable=True),
    help="Path to save decks to. Defaults to saving indivdual decks to their "
    "own files named after their sources, but with the extension .apkg.",
)
@click.pass_obj
def build(options, decks, output):
    """Build an Anki package from deck files."""
    package = genanki.Package([])  # Only used with --output

    for deck in read_decks(decks, options.cache_path, options.reprocess):
        if output is None:
            # Automatically figures out the path to save to.
            deck.save_to_file()
        else:
            deck.save_to_package(package)

    if output:
        package.write_to_file(output)
        LOGGER.info(f"Wrote decks to file {output}")


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="UTF-8"))
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
    """Print information about every note in the passed format."""
    for deck in read_decks(decks, options.cache_path, options.reprocess):
        for note in deck.notes.values():
            print(
                ### FIXME document variables
                format.format(
                    note_id=note.note_id(deck_id=deck.id()),
                    deck=deck.title(),
                    deck_id=deck.id(),
                    **note.variables(),
                )
            )


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="UTF-8"))
@click.pass_obj
def dump_videos(options, decks):
    """
    Make sure the videos from the deck are downloaded to the cache and display
    the path to each one.
    """
    for deck in read_decks(decks, options.cache_path, options.reprocess):
        print(f"title: {deck.title()}")
        for id, note in deck.notes.items():
            print(f'{", ".join(note.media_paths())} {note.text()}')


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="UTF-8"))
@click.pass_obj
def to_html(options, decks):
    """Display decks as HTML on stdout."""
    for deck in read_decks(decks, options.cache_path, options.reprocess):
        print(htmlize_deck(deck, path_prefix=options.cache_path))


@cli.command()
@click.argument("decks", nargs=-1, type=click.File("r", encoding="UTF-8"))
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
def serve_http(options, decks, bind, run_seconds):
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
    for deck in read_decks(decks, options.cache_path, options.reprocess):
        file_name = deck.title().replace("/", "--") + ".html"
        html_path = os.path.join(options.cache_path, file_name)
        if html_path in html_written:
            raise KeyError(
                f"Duplicate path after munging deck title: {html_path}"
            )
        html_written.add(html_path)

        with open(html_path, "w", encoding="utf-8") as file:
            file.write(htmlize_deck(deck, path_prefix=""))

        deck_links.append((file_name, deck))

    # FIXME serve html from memory so that you can run multiple copies of
    # this tool at once.
    index_path = os.path.join(options.cache_path, "index.html")
    with open(index_path, "w", encoding="utf-8") as file:
        file.write(generate_index_html(deck_links))

    # FIXME it would be great to just serve this directory as /static without
    # needing the symlink.
    ensure_static_link(options.cache_path)

    Handler = functools.partial(
        server.SimpleHTTPRequestHandler, directory=options.cache_path
    )
    httpd = server.HTTPServer((address, port), Handler)

    print(f"Starting HTTP server on http://{bind}/")
    if run_seconds is None:
        httpd.serve_forever()
    else:
        threading.Thread(target=httpd.serve_forever).start()
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
        video = Video(
            url, cache_path=options.cache_path, reprocess=options.reprocess
        )
        open_in_app([video.processed_video()])


@cli.command()
@click.argument("files", nargs=-1, type=click.File("r", encoding="UTF-8"))
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
        for url in file:
            url = url.strip()
            if not url:
                next

            try:
                video = Video(
                    url,
                    cache_path=options.cache_path,
                    reprocess=options.reprocess,
                )
                open_in_app([video.processed_video()])
            except BadURL as error:
                print(f"Error: {error}")
            except yt_dlp.utils.DownloadError:
                # yt_dlp prints the error itself.
                pass


def read_deck_specs(files):
    parser = DeckParser()
    for file in files:
        yield from parser.parse_file(file)


def read_decks(files, cache_path, reprocess=False):
    for spec in read_deck_specs(files):
        yield Deck(spec, cache_path=cache_path, reprocess=reprocess)


def path_to_web_files():
    from os.path import join, dirname, realpath

    return join(dirname(dirname(realpath(__file__))), "web-files")


def ensure_static_link(cache_path):
    web_files_path = path_to_web_files()
    static_path = os.path.join(cache_path, "static")

    try:
        os.symlink(web_files_path, static_path)
    except FileExistsError:
        if os.readlink(static_path) == web_files_path:
            # Symlink already exists
            return

    try:
        os.remove(static_path)
    except Exception as e:
        sys.exit(f"Error removing {static_path} replace with symlink: {e}")

    try:
        os.symlink(web_files_path, static_path)
    except Exception as e:
        sys.exit(f"Error symlinking {static_path} to {web_files_path}: {e}")


def static_url(path):
    mtime = os.path.getmtime(os.path.join(path_to_web_files(), path))
    return f"/static/{path}?{mtime}"


def generate_index_html(deck_links):
    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Decks</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url('general.css')}">
      </head>
      <body>
        <h1>Decks</h1>

        <ol>"""

    for file_name, deck in deck_links:
        if deck.title() is None:
            sys.exit(f"Deck {repr(deck.source_path())} does not contain title")

        output += f"""
          <li><a href="./{h(file_name)}">{h(deck.title())}</a></li>"""

    return textwrap.dedent(
        output
        + """
        </ol>
      </body>
    </html>"""
    ).lstrip()


def htmlize_deck(deck, path_prefix=""):
    if deck.title() is None:
        sys.exit(f"Deck {repr(deck.source_path())} does not contain title")

    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{h(deck.title())}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url('general.css')}">
      </head>
      <body>
        <h1>{h(deck.title())}</h1>"""

    for note in deck.notes.values():
        more_html = note.more_field().render_html(path_prefix)
        if more_html != "":
            more_html = f'<div class="more">{more_html}</div>'
        output += f"""
        <div class="note">
          <h3>{note.text_field().render_html(path_prefix)}</h3>
          {note.media_field().render_html(path_prefix)}
          {more_html}
          <p class="note_id">{h(note.note_id())}</p>
        </div>"""

    return textwrap.dedent(
        output
        + """
      </body>
    </html>"""
    ).lstrip()


def h(s):
    return html.escape(s)


def open_in_app(arguments):
    # FIXME only works on macOS and Linux; should handle command not found.
    if os.uname().sysname == "Darwin":
        subprocess.run(["open", *arguments], check=True)
    elif os.uname().sysname == "Linux":
        subprocess.run(["xdg-open", *arguments], check=True)
    else:
        raise RuntimeError(
            f"Don’t know how to open {repr(arguments)} on this platform."
        )
