from pathlib import Path


def path_to_web_files() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "web-files"


def static_url(path) -> str:
    mtime = (path_to_web_files() / "static" / path).stat().st_mtime
    return f"static/{path}?{mtime}"
