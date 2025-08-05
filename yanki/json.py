from collections.abc import Callable
from pathlib import Path


def update_media_paths(
    note: dict,
    media_dir: Path,
    *,
    install_method: Callable[[Path, Path], Path],
    media_prefix: str | None = None,
):
    """Update media paths in a JSON Note.

    This installs media paths into the `media_dir` with `install_method`, which
    must be one of:

        * `yanki.util.copy_into`
        * `yanki.util.hardlink_into`
        * `yanki.util.symlink_into`

    It updates `note["media_paths"]` with the new paths to the media, OR to have
    same file name as the new media, but using the prefix `media_prefix` (which
    should end with a `/`).
    """
    new_paths = []
    for source in note["media_paths"]:
        destination = install_method(Path(source), media_dir)
        if media_prefix is None:
            new_paths.append(str(destination))
        else:
            new_paths.append(f"{media_prefix}{destination.name}")

    note["media_paths"] = new_paths
