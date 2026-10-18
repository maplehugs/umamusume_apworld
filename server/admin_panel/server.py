"""The panel's local web server: the static desktop UI, game icons, and one
JSON endpoint that forwards an operation to a region's worker.

    GET  /                               the desktop
    GET  /icons/<kind>/<id>              game art (icons.py)
    GET  /api/status                     worker status per region
    POST /api/<region>/<op>              {viewer?, args?} -> {result, log, history}
    POST /api/<region>/_restart          restart that region's worker

Errors come back as {error, detail} with HTTP 400 (refusals) or 500.

Binds to 127.0.0.1 only and refuses foreign Host / Origin headers (the same
guard VivloToolkit uses), so other websites can't drive it through your
browser. This panel edits saves directly: never expose it to a network.
"""

from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import icons
from .workers import Pool, WorkerError

STATIC = (Path(__file__).resolve().parent / "static").resolve()
MAX_BODY = 128 * 1024 * 1024        # whole-save imports can be tens of MB


class Handler(BaseHTTPRequestHandler):
    server: "PanelServer"

    def log_message(self, *_):
        pass

    def _allowed(self) -> bool:
        ok = {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}", *self.server.extra_hosts}
        if self.headers.get("Host") not in ok:
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlsplit(origin).netloc in ok

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json", cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode())

    def do_GET(self):
        if not self._allowed():
            return self._send(403, b"forbidden", "text/plain")
        path = urlsplit(self.path).path
        if path == "/api/status":
            return self._json(200, self.server.pool.status())
        if path.startswith("/custom-icons/"):
            import base64
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[1] not in ("global", "jp") or parts[2] not in ("support", "supportart"):
                return self._send(404)
            try:
                r = self.server.pool.call(parts[1], "custom_support.art", None, {"id": int(parts[3])})["result"]
                art = r.get("art", "")
                body = base64.b64decode(art.removeprefix("data:image/png;base64,")) if art else icons.get(parts[2], r["donor"])
                return self._send(200, body, "image/png") if body else self._send(404)
            except (ValueError, WorkerError):
                return self._send(404)
        if path.startswith("/icons/"):
            parts = path.strip("/").split("/")
            try:
                body = icons.get(parts[1], int(parts[2])) if len(parts) == 3 else None
            except ValueError:
                body = None
            if body is None:
                # Not cached: icons.py remembers real misses, and a transient miss
                # must not stick in the browser after the icon becomes available.
                return self._send(404, b"no icon", "text/plain", "no-store")
            return self._send(200, body, "image/png", "max-age=604800")
        if path == "/":
            path = "/index.html"
        file = (STATIC / path.lstrip("/")).resolve()
        if not file.is_file() or STATIC not in file.parents:
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if file.suffix == ".js":
            ctype = "text/javascript"
        cache = "max-age=31536000, immutable" if file.suffix == ".woff2" else "no-cache"
        self._send(200, file.read_bytes(), ctype, cache)

    def do_POST(self):
        if not self._allowed():
            return self._send(403, b"forbidden", "text/plain")
        parts = urlsplit(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api":
            return self._json(404, {"error": "No such endpoint."})
        region, op = parts[1], parts[2]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"error": "Request too large."})
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if op == "_restart":
                self.server.pool.restart(region)
                return self._json(200, {"result": {"restarted": region}})
            msg = self.server.pool.call(region, op, body.get("viewer"), body.get("args") or {})
            self._json(200, {"result": msg.get("result"), "log": msg.get("log") or "",
                             "history": msg.get("history") or []})
        except WorkerError as ex:
            self._json(400, {"error": str(ex), "detail": ex.detail})
        except Exception as ex:  # noqa: BLE001
            self._json(500, {"error": f"{type(ex).__name__}: {ex}", "detail": traceback.format_exc()})


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, extra_hosts=()):
        super().__init__(("127.0.0.1", port), Handler)
        self.port = self.server_address[1]
        self.extra_hosts = frozenset(extra_hosts)
        self.pool = Pool()
