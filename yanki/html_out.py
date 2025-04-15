from html import escape as h
import os
from pathlib import Path
import sys
import textwrap


def generate_index_html(deck_links):
    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Decks</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url("general.css")}">
      </head>
      <body>
        <h1>Decks</h1>

        <ol>"""

    for file_name, deck in deck_links:
        if deck.title is None:
            sys.exit(f"Deck {deck.source_path!r} does not contain title")

        output += f"""
          <li><a href="./{h(file_name)}">{h(deck.title)}</a></li>"""

    return textwrap.dedent(
        output
        + """
        </ol>
      </body>
    </html>"""
    ).lstrip()


def htmlize_deck(deck, path_prefix="", flash_cards=False):
    if deck.title is None:
        sys.exit(f"Deck {deck.source_path!r} does not contain title")

    if flash_cards:
        flash_cards_html = f"""
        <link rel="stylesheet" href="{static_url("flash-cards.css")}">
        <script src="{static_url("flash-cards.js")}" async></script>
        """
    else:
        flash_cards_html = ""

    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{h(deck.title)}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url("general.css")}">
        {flash_cards_html}
      </head>
      <body>
        <h1>{h(deck.title)}</h1>"""

    for note in sorted(deck.notes(), key=lambda note: note.spec.line_number):
        if more_html := note.more_field().render_html(path_prefix):
            more_html = f'<div class="more">{more_html}</div>'
        if clip := note.spec.clip_or_trim():
            clip_html = h("@" + "-".join([str(time) for time in clip]))
        else:
            clip_html = ""

        output += f"""
        <div class="note">
          <h3>{note.text_field().render_html(path_prefix)}</h3>
          <div class="media">
              {note.media_field().render_html(path_prefix)}
          </div>
          {more_html}
          <table class="metadata">
            <tr class="direction">
              <th>Direction:</th>
              <td>media <span>{h(note.spec.direction())}</span> text</td>
            </tr>
            <tr class="note_id">
              <th>Note ID:</th>
              <td>{h(note.note_id)}</td>
            </tr>
            <tr class="source">
              <th>Source:</th>
              <td>
                <span>{h(note.spec.source_path)}</span>
                line <span>{h(str(note.spec.line_number))}</span>
              </td>
            </tr>
            <tr class="media">
              <th>Media:</th>
              <td>
                <a href="{h(note.spec.video_url())}">{h(note.spec.video_url())}</a>
                {clip_html}
              </td>
            </tr>
          </table>
        </div>"""

    return textwrap.dedent(
        output
        + """
      </body>
    </html>"""
    ).lstrip()


def ensure_static_link(cache_path: Path):
    web_files_path = path_to_web_files()
    static_path = cache_path / "static"

    try:
        static_path.symlink_to(web_files_path)
    except FileExistsError:
        if static_path.readlink() == web_files_path:
            # Symlink already exists
            return

    try:
        static_path.unlink()
    except Exception as e:
        sys.exit(f"Error removing {static_path} to replace with symlink: {e}")

    try:
        static_path.symlink_to(web_files_path)
    except Exception as e:
        sys.exit(f"Error symlinking {static_path} to {web_files_path}: {e}")


def path_to_web_files() -> Path:
    return Path(__file__).resolve().parent.parent / "web-files"


def static_url(path) -> str:
    mtime = os.path.getmtime(path_to_web_files() / path)
    return f"/static/{path}?{mtime}"
