from pathlib import Path
from tempfile import TemporaryDirectory

CACHEDIR_TAG_CONTENT = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by Yanki.
# For information about cache directory tags, see:
#	https://bford.info/cachedir/
#
# For information about yanki, see:
#   https://github.com/danielparks/Yanki
"""


class Cache:
    """Trivial class to manage a cache directory."""

    def __init__(self, path: Path | None = None):
        """Set up the cache directory."""
        self.path = path
        if self.path is None:
            self.temporary_directory = TemporaryDirectory()
            self.path = Path(self.temporary_directory.name)
        self.ensure()

    def ensure(self):
        """Make sure cache is set up.

        Called by __init__().
        """
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "CACHEDIR.TAG").write_text(
            CACHEDIR_TAG_CONTENT, encoding="ascii"
        )
