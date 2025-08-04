import re
from multiprocessing import cpu_count
from pathlib import Path

import click

from yanki.cli import cli

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def test_yanki_help():
    readme_text = (PACKAGE_ROOT / "README.md").read_text()
    examples = re.findall(
        r"\n```\n❯ uvx yanki --help\n(.+?)\n```\n", readme_text, re.DOTALL
    )
    assert len(examples) >= 1, "Could not find --help text in README.md"

    with click.Context(cli, info_name="yanki") as ctx:
        help = cli.get_help(ctx).replace(
            f"$YANKI_CONCURRENCY or {cpu_count()}]",
            "$YANKI_CONCURRENCY or 4]",
        )
        for example in examples:
            assert help == example, "--help does not match example in README.md"
