import functools
import http.server
import threading
import time
from dataclasses import dataclass

import click

from yanki.utils import open_in_app


@dataclass(frozen=True)
class Server:
    """Configuration for HTTP server options."""

    open: bool = False
    bind: str = "localhost:8000"

    def __post_init__(self):
        """Validate the configuration."""
        # Trigger validation by accessing the cached property
        self.bind_tuple  # noqa: B018 (not actually useless)

    @functools.cached_property
    def bind_tuple(self) -> tuple[str, int]:
        """Split --bind value into (address, port) and validate.

        Raises:
            click.UsageError: If bind format is invalid.
        """
        bind_parts = self.bind.split(":")
        if len(bind_parts) != 2:
            raise click.UsageError("--bind must be in address:port format.")

        address, port_str = bind_parts

        try:
            port = int(port_str)
        except ValueError as error:
            raise click.UsageError("--bind expects an integer port.") from error

        if not (1 <= port <= 65535):
            raise click.UsageError("--bind port must be between 1 and 65535.")

        return (address, port)

    @property
    def bind_address(self) -> str:
        """Get the address to bind to from --bind."""
        return self.bind_tuple[0]

    @property
    def bind_port(self) -> int:
        """Get the port to bind to from --bind."""
        return self.bind_tuple[1]

    def serve_forever(self, directory="."):
        """Start the HTTP server in `directory`."""

        def open_browser():
            time.sleep(0.5)
            open_in_app([f"http://localhost:{self.bind_port}/"])

        httpd = http.server.HTTPServer(
            self.bind_tuple,
            functools.partial(
                http.server.SimpleHTTPRequestHandler, directory=directory
            ),
        )

        if self.open:
            threading.Thread(target=open_browser).start()

        print(f"Starting HTTP server on http://{self.bind}/")
        httpd.serve_forever()


def server_options(func):
    """Add common server options to a command.

    Adds the following options:
    - --open: Open in web browser
    - --bind: Address to bind the HTTP server to

    The decorated function must take a `server` parameter of type `Server`.
    """

    @click.option(
        "-o",
        "--open/--no-open",
        default=False,
        help="Open the server URL in a web browser.",
    )
    @click.option(
        "-b",
        "--bind",
        default="localhost:8000",
        show_default=True,
        metavar="ADDRESS:PORT",
        help="Address and port to start the HTTP server on.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Removes server options from kwargs:
        kwargs["server"] = Server(
            open=kwargs.pop("open"),
            bind=kwargs.pop("bind"),
        )

        return func(*args, **kwargs)

    return wrapper
