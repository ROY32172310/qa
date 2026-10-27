"""Small static server used by the CLI for local directories."""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


class LocalServer:
    def __init__(self, root: str | Path) -> None:
        directory = Path(root).resolve()
        if not directory.is_dir():
            raise ValueError(f"local directory does not exist: {directory}")
        handler = functools.partial(_QuietHandler, directory=str(directory))
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def url(self, filename: str = "index.html") -> str:
        clean = filename.lstrip("/")
        return f"http://127.0.0.1:{self.port}/{clean}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def __enter__(self) -> LocalServer:
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.close()
