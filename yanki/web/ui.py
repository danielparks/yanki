import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from yanki.anki import FinalDeck
from yanki.json import update_media_paths
from yanki.tree import tree, tree_node_json_encoder
from yanki.utils import (
    create_unique_file,
    url_friendly_name,
)
from yanki.web import path_to_web_files

LOGGER = logging.getLogger(__name__)


def save_flashcard_html_to(
    root: Path,
    decks: Iterable[FinalDeck],
    *,
    install_method: Callable[[Path, Path], Path],
):
    """Save HTML and assets for web flashcard UI.

    Uses `install_method` to install assets into the `root` directory. It should
    be one of:

        * `yanki.util.copy_into`
        * `yanki.util.hardlink_into`
        * `yanki.util.symlink_into`
    """
    web_files = path_to_web_files()

    media_dir = root / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    deck_dir = root / "decks"
    deck_dir.mkdir(exist_ok=True)

    install_method(web_files / "static", root)

    deck_index = []
    for deck in decks:
        deck_json = deck.to_dict(base_url="media")
        for note in deck_json["notes"]:
            update_media_paths(
                note,
                media_dir,
                install_method=install_method,
                media_prefix="media/",
            )

        # Create the deck JSON file.
        name = url_friendly_name(deck.title)
        with create_unique_file(deck_dir / f"{name}.json") as file:
            LOGGER.debug(f"Saving {deck.title!r} into {file.name!r}")
            json.dump(deck_json, file)
            deck_index.append(
                {
                    "title": deck.title,
                    "path": f"decks/{Path(file.name).name}",
                }
            )

    decks_tree_json = json.dumps(
        tree(
            deck_index,
            key=lambda deck: deck["title"].split("::"),
            root_name="Decks",
        ),
        default=tree_node_json_encoder,
    )

    # Generate index.html
    index_html = (web_files / "templates/flashcards.html").read_text()
    for path in (web_files / "static").glob("*"):
        index_html = index_html.replace(
            f'"static/{path.name}"',
            f'"static/{path.name}?{path.stat().st_mtime}"',
        )
    index_html = index_html.replace("{ DECKS }", decks_tree_json)
    (root / "index.html").write_text(index_html)
