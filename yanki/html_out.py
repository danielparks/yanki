import shutil
import sys
from collections import OrderedDict
from html import escape as h
from pathlib import Path

from yanki.utils import file_safe_name


class DeckTree:
    def __init__(self, name=None):
        self.children = OrderedDict()
        self.name = name
        self.deck = None
        self.deck_file_name = None
        self.index_file_name = None

    def __getitem__(self, key):
        if key not in self.children:
            self.children[key] = DeckTree(name=key)
        return self.children[key]

    def dig(self, path):
        if len(path):
            return self[path[0]].dig(path[1:])
        return self


def write_html(output_path, cache_path, decks, *, flashcards=False):
    """Write HTML version of decks to a path."""
    if output_path == cache_path:
        # Serving HTML from the cache; no need to copy media.
        output_media_path = None
        ensure_static_link(output_path)
    else:
        # Generating a fresh output directory; copy media.
        output_path.mkdir(parents=True, exist_ok=True)
        output_media_path = output_path
        shutil.copytree(
            path_to_web_files(), output_path / "static", dirs_exist_ok=True
        )

    if len(decks) == 1:
        # Special case: single deck goes in index.html
        deck = decks[0]
        if deck.title is None:
            sys.exit(f"Deck {deck.source_path!r} does not contain title")
        write_deck_files(
            output_path / "index.html",
            output_media_path,
            deck,
            [(name, None) for name in deck.title.split("::")],
            flashcards=flashcards,
        )
        return

    # Figure out file names for decks.
    decks_by_path = {}
    deck_tree = DeckTree()
    for deck in decks:
        if deck.title is None:
            sys.exit(f"Deck {deck.source_path!r} does not contain title")

        file_name = "deck_" + file_safe_name(deck.title) + ".html"
        html_path = output_path / file_name
        if html_path in decks_by_path:
            raise KeyError(
                f"Decks with titles {decks_by_path[html_path].title!r} and "
                f"{deck.title!r} would both to write to file {html_path!r}"
            )
        decks_by_path[html_path] = deck

        title_parts = deck.title.split("::")
        leaf = deck_tree.dig(title_parts)
        leaf.deck_file_name = file_name
        leaf.deck = deck

    write_tree_indices(
        deck_tree, output_path, output_media_path, flashcards=flashcards
    )


def write_tree_indices(
    tree, output_path, output_media_path, *, title_path=None, flashcards=False
):
    if title_path is None:
        title_path = []
    if tree.deck_file_name is None and title_path == [] and tree.name is None:
        # Anonymous root.
        if len(tree.children) == 1:
            # If there is exactly one child of the anonymous root, then skip it.
            return write_tree_indices(
                next(iter(tree.children.values())),
                output_path,
                output_media_path,
                flashcards=flashcards,
            )
        # Anonymous root has zero or more than one child deck.
        tree.name = "Decks"

    if len(tree.children) == 0:
        if tree.deck_file_name:
            # A tree with a deck is created with `deck_tree.dig()`, so it should
            # always have a name.
            assert tree.name is not None  # noqa: S101
            write_deck_files(
                output_path / tree.deck_file_name,
                output_media_path,
                tree.deck,
                [*title_path, (tree.name, tree.deck_file_name)],
                flashcards=flashcards,
            )
            return (
                f'<li><a href="{h(tree.deck_file_name)}">{h(tree.name)}'
                "</a></li>"
            )
        return ""

    # Has child decks. Must have a name.
    assert tree.name is not None  # noqa: S101
    if title_path == []:
        tree.index_file_name = "index.html"
    else:
        title_names = [name for name, _ in title_path] + [tree.name]
        tree.index_file_name = (
            "index_" + file_safe_name("::".join(title_names)) + ".html"
        )

    # This rebinds the variable to a new value instead of changing the old
    # title_path object like .append() or += would:
    title_path = [*title_path, (tree.name, tree.index_file_name)]

    list_html = [
        write_tree_indices(
            child,
            output_path,
            output_media_path,
            title_path=title_path,
            flashcards=flashcards,
        )
        for child in tree.children.values()
    ]
    list_html = "<ol>\n      " + "\n      ".join(list_html) + "\n    </ol>"
    title_html = f'<a href="{h(tree.index_file_name)}">{h(tree.name)}</a>'
    if tree.deck_file_name:
        write_deck_files(
            output_path / tree.deck_file_name,
            output_media_path,
            tree.deck,
            [*title_path, ("Deck", tree.deck_file_name)],
            flashcards=flashcards,
        )
        deck_link = f'<a href="{h(tree.deck_file_name)}">Deck</a>'
        title_html += f" ({deck_link})"
    else:
        deck_link = ""

    (output_path / tree.index_file_name).write_text(
        generate_index_html(deck_link, list_html, title_path), encoding="utf_8"
    )
    return f"""<li>
        <h3>{title_html}</h3>
        {list_html}
      </li>"""


def generate_index_html(deck_link_html, child_html, title_path):
    return f"""
        <!DOCTYPE html>
        <html>
          <head>
            <title>{title_html(title_path, add_links=False)}</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="stylesheet" href="{static_url("general.css")}">
          </head>
          <body>
            <h1>{title_html(title_path, final_link=False)}</h1>
            {deck_link_html}
            {child_html}
          </body>
        </html>
        """.replace("\n        ", "\n").lstrip()


def write_deck_files(
    html_path, output_media_path, deck, title_path, *, flashcards=False
):
    html_path.write_text(
        htmlize_deck(deck, title_path, path_prefix="", flashcards=flashcards),
        encoding="utf_8",
    )

    # Copy media to output.
    if output_media_path is not None:
        for path in deck.media_paths():
            output_path = output_media_path / Path(path).name
            shutil.copy2(path, output_path)
            # Make sure media is accessible by the web server.
            output_path.chmod(0o644)


def htmlize_deck(deck, title_path, *, path_prefix="", flashcards=False):
    if deck.title is None:
        sys.exit(f"Deck {deck.source_path!r} does not contain title")

    if flashcards:
        flashcards_html = f"""
        <link rel="stylesheet" href="{static_url("flashcards.css")}">
        <script src="{static_url("flashcards.js")}" async></script>
        """
    else:
        flashcards_html = ""

    output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{title_html(title_path, add_links=False)}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="{static_url("general.css")}">
        {flashcards_html}
      </head>
      <body>
        <h1>{title_html(title_path, final_link=False)}</h1>"""

    for note in deck.notes():
        if more_html := note.more_field().render_html(path_prefix):
            more_html = f'<div class="more">{more_html}</div>'
        if clip := note.spec.clip_or_trim():
            clip_html = h("@" + "-".join([str(time) for time in clip]))
        else:
            clip_html = ""

        video_url_html = h(note.spec.video_url())
        output += f"""
        <div class="note">
          <div class="cards">
            <h3>{note.text_field().render_html(path_prefix)}</h3>
            <div class="media">
              {note.media_field().render_html(path_prefix)}
            </div>
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
                <a href="{video_url_html}">{video_url_html}</a>
                {clip_html}
              </td>
            </tr>
          </table>
        </div>"""

    return f"""{output}
      </body>
    </html>
    """.replace("\n    ", "\n").lstrip()


def title_html(title_path, *, add_links=True, final_link=True):
    if not title_path:
        return ""
    if not add_links:
        return h(" ❯ ".join([name for name, _ in title_path]))

    html = [
        f'<a href="{h(file_name)}">{h(name)}</a>' if file_name else h(name)
        for name, file_name in title_path
    ]

    if not final_link:
        # Replace final link with plain text.
        name, _ = title_path[-1]
        html[-1] = h(name)

    return " ❯ ".join(html)


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
    except OSError as e:
        sys.exit(f"Error removing {static_path} to replace with symlink: {e}")

    try:
        static_path.symlink_to(web_files_path)
    except OSError as e:
        sys.exit(f"Error symlinking {static_path} to {web_files_path}: {e}")


def path_to_web_files() -> Path:
    return Path(__file__).resolve().parent.parent / "web-files"


def static_url(path) -> str:
    mtime = (path_to_web_files() / path).stat().st_mtime
    return f"static/{path}?{mtime}"
