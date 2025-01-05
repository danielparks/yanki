from html import escape as h
from os.path import dirname, realpath
import os
import sys
import textwrap


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
        if deck.title is None:
            sys.exit(f"Deck {repr(deck.source_path)} does not contain title")

        output += f"""
          <li><a href="./{h(file_name)}">{h(deck.title)}</a></li>"""

    return textwrap.dedent(
        output
        + """
        </ol>
      </body>
    </html>"""
    ).lstrip()


def htmlize_deck(deck, path_prefix=""):
    if deck.title is None:
        sys.exit(f"Deck {repr(deck.source_path)} does not contain title")

    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{h(deck.title)}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url('general.css')}">
      </head>
      <body>
        <h1>{h(deck.title)}</h1>"""

    for note in deck.notes():
        more_html = note.more_field().render_html(path_prefix)
        if more_html != "":
            more_html = f'<div class="more">{more_html}</div>'
        output += f"""
        <div class="note">
          <h3>{note.text_field().render_html(path_prefix)}</h3>
          {note.media_field().render_html(path_prefix)}
          {more_html}
          <p class="note_id">{h(note.note_id)}</p>
        </div>"""

    return textwrap.dedent(
        output
        + """
      </body>
    </html>"""
    ).lstrip()


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


def path_to_web_files():
    return os.path.join(dirname(dirname(realpath(__file__))), "web-files")


def static_url(path):
    mtime = os.path.getmtime(os.path.join(path_to_web_files(), path))
    return f"/static/{path}?{mtime}"
