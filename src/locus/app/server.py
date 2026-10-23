"""Tiny dependency-free HTTP server for the generated dashboard and JSON API."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar


class LocusHandler(SimpleHTTPRequestHandler):
    directory: Path = Path(".")
    api: ClassVar[dict[str, Path]] = {}

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._serve_api()
            return
        if self.path in {"", "/"}:
            self.path = "/dashboard.html"
        super().do_GET()

    def _serve_api(self) -> None:
        endpoint = self.path.split("?", 1)[0].rstrip("/")
        if endpoint == "/api/health":
            self._json({"status": "ok"})
            return
        path = self.api.get(endpoint)
        if path is None or not path.exists():
            self._json({"error": "not_found"}, status=404)
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._json(payload)

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        # Keep the demo dashboard fresh after re-running the pipeline.
        if self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        if self.path.startswith("/api/") or self.path == "/":
            return


def build_server(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Create the HTTP server (useful for tests and embedding)."""

    directory = directory.resolve()
    if not (directory / "dashboard.html").exists():
        raise FileNotFoundError(
            f"{directory / 'dashboard.html'} not found. Run `locus demo` first."
        )

    class ConfiguredHandler(LocusHandler):
        pass

    ConfiguredHandler.api = {
        "/api/locations": directory / "location_index.geojson",
        "/api/pois": directory / "pois.geojson",
        "/api/summary": directory / "summary.json",
    }
    handler = partial(ConfiguredHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def serve(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
) -> None:
    directory = directory.resolve()
    server = build_server(directory, host=host, port=port)
    url = f"http://{host}:{port}/"
    print(f"Locus dashboard: {url}")
    print(f"JSON API:        {url}api/summary")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
