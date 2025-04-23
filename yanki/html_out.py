from collections import defaultdict
from html import escape as h
import os
from pathlib import Path
import shutil
import sys
import textwrap
from yanki.utils import file_safe_name


def write_html(output_path, cache_path, decks, flash_cards=False):
    """Write HTML version of decks to a path."""
    deck_links = []
    html_written = set()

    output_path.mkdir(parents=True, exist_ok=True)

    for deck in decks:
        file_name = "deck_" + file_safe_name(deck.title) + ".html"
        html_path = output_path / file_name
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

        if output_path != cache_path:
            # Copy media to output.
            for path in deck.media_paths():
                shutil.copy2(path, output_path / os.path.basename(path))

        deck_links.append((file_name, deck))

    index_path = output_path / "index.html"
    index_path.write_text(generate_index_html(deck_links), encoding="utf_8")

    indices = defaultdict(list)
    for file_name, deck in deck_links:
        title = deck.title.split("::")
        for i in range(1, len(title) + 1):
            partial = "::".join(title[:i])
            indices[partial].append((file_name, deck))

    for partial, deck_links in indices.items():
        file_name = "index_" + file_safe_name(partial) + ".html"
        index_path = output_path / file_name
        index_path.write_text(
            generate_index_html(deck_links, partial), encoding="utf_8"
        )

    if output_path == cache_path:
        ensure_static_link(output_path)
    else:
        shutil.copytree(
            path_to_web_files(), output_path / "static", dirs_exist_ok=True
        )


def generate_index_html(deck_links, title="Decks"):
    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{title_html(title, False)}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url("general.css")}">
      </head>
      <body>
        <h1>{title_html(title, final_link=None)}</h1>

        <ol>"""

    for file_name, deck in deck_links:
        if deck.title is None:
            sys.exit(f"Deck {deck.source_path!r} does not contain title")

        output += f"""
          <li>{deck_title_html(deck, final_link="deck", rm_prefix=title)}</li>"""

    return textwrap.dedent(
        output
        + """
        </ol>
      </body>
    </html>
    """
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
        <title>{deck_title_html(deck, False)}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url("general.css")}">
        {flash_cards_html}
      </head>
      <body>
        <h1>{deck_title_html(deck, final_link=None)}</h1>"""

    for note in deck.notes():
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
    </html>
    """
    ).lstrip()


def deck_title_html(deck, add_links=True, final_link="deck", rm_prefix=None):
    return title_html(
        deck.title,
        add_links=add_links,
        final_link=final_link,
        rm_prefix=rm_prefix,
    )


def title_html(title, add_links=True, final_link="deck", rm_prefix=None):
    if rm_prefix and title.startswith(rm_prefix):
        rm_prefix = rm_prefix.count("::") + 1
    else:
        rm_prefix = 0

    title = title.split("::")
    if not add_links:
        return h(" ❯ ".join(title[rm_prefix:]))

    parts = []
    path = []
    for part in title[:-1]:
        path.append(part)
        partial = file_safe_name("::".join(path))
        parts.append(f'<a href="index_{h(partial)}.html">{h(part)}</a>')

    if title[-1]:
        if final_link is None:
            parts.append(f"{h(title[-1])}")
        else:
            partial = file_safe_name("::".join(title))
            parts.append(
                f'<a href="{final_link}_{h(partial)}.html">{h(title[-1])}</a>'
            )

    return " ❯ ".join(parts[rm_prefix:])


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
    return f"static/{path}?{mtime}"
