"""Loopback side channel the Hachimi plugin arms itself from, plus the
session source transport.open_request reads.

The plugin (tools/hachimi_jp_localserver) patches the client to seal to OUR
public key, but only while this listener answers -- so "patched client talking
to the real Cygames server" (the handoff's one real hazard) needs the redirect
AND a live local server, not just a forgotten plugin. Before each patch it
sends:

    GET /arm?tail20=<hex>&udid=<hex>&tail50=<hex or empty>   ->  200 <pubkey hex>

tail20   pre52[32:52], the per-build KDF constant. Never on the wire and it
         rotates on client updates, so the client is the only honest source.
udid,    the session constants of a client that ALREADY has an account (its
tail50   SaveData holds a Cygames-issued auth_key). This is what lets the
         client log in as itself without a signup, and without us ever writing
         its save file.

⛔ The reported tail50 of an existing account IS that account's real Cygames
credential, so it lives in memory only -- never in accounts_jp.sqlite3, which
is tracked in git. The plugin re-reports it on every arm, so nothing is lost.
Accounts WE mint at tool/signup are ordinary local accounts and are stored.

Plain HTTP on 127.0.0.1 only: the plugin runs in the same machine's game
process and has no reason to speak TLS.
"""

from __future__ import annotations

import base64
import json
import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import accounts, region
from . import keys, transport

log = logging.getLogger("uma-server")

# The Hachimi plugin dials 8090; the override exists for tests beside a running server.
PORT = int(os.environ.get("UMA_JP_ARM_PORT", "8090"))
# A phone on the tailnet dials <server host>:8090, so serving it remotely sets this.
HOST = os.environ.get("UMA_JP_ARM_HOST", "127.0.0.1")


def _tail20_path():
    with region.use_region("jp"):
        return region.data_dir() / "build_tail20.json"


_lock = threading.Lock()
_tail20: list[bytes] = []                     # learned, newest first
_reported: dict[str, bytes] = {}              # udid hex -> tail50 (memory only, see above)
_last_udid: str | None = None


def _load_tail20() -> None:
    try:
        vals = json.loads(_tail20_path().read_text())
        _tail20[:] = [bytes.fromhex(v) for v in vals]
    except (OSError, ValueError):
        pass


def _learn(tail20: bytes | None, udid: bytes | None, tail50: bytes | None) -> None:
    global _last_udid
    with _lock:
        if tail20 and len(tail20) == 20 and (not _tail20 or _tail20[0] != tail20):
            if tail20 in _tail20:
                _tail20.remove(tail20)
            _tail20.insert(0, tail20)
            _tail20_path().write_text(json.dumps([t.hex() for t in _tail20[:8]]))
            if tail20 not in transport.KNOWN_TAIL20:
                log.warning("JP: client reported a NEW build tail20 %s -- a client update; "
                            "add it to transport.KNOWN_TAIL20", tail20.hex())
        if udid and len(udid) == 16 and tail50 and len(tail50) == 50:
            if _reported.get(udid.hex()) != tail50:
                log.info("JP: plugin reported an existing session udid=%s..", udid.hex()[:12])
            _reported[udid.hex()] = tail50
            _last_udid = udid.hex()


class Sessions:
    """transport.SessionSource: minted accounts first, then what the plugin reported."""

    def session_for(self, viewer_id: str) -> transport.Session | None:
        acct = accounts.get_account(viewer_id) if viewer_id not in ("", "0") else None
        if acct and acct.get("udid") and acct.get("auth_key"):
            return transport.Session(udid=bytes.fromhex(acct["udid"]),
                                     tail50=base64.b64decode(acct["auth_key"]))
        with _lock:
            if _last_udid and _last_udid in _reported:
                return transport.Session(udid=bytes.fromhex(_last_udid),
                                         tail50=_reported[_last_udid])
        return None

    def reported_sessions(self) -> list[transport.Session]:
        """Every session the plugin reported, newest first."""
        with _lock:
            items = list(_reported.items())[::-1]
        return [transport.Session(udid=bytes.fromhex(u), tail50=t) for u, t in items]

    def tail20_candidates(self):
        with _lock:
            return list(_tail20)


SESSIONS = Sessions()


def _hex(qs: dict, key: str) -> bytes | None:
    try:
        v = (qs.get(key) or [""])[0]
        return bytes.fromhex(v) if v else None
    except ValueError:
        return None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):          # the default logger writes to stderr per call
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/log":
            # iOS Hachimi redirect mirrors its status lines here.
            try:
                log.info("PHONE: %s", bytes.fromhex(parse_qs(url.query).get("m", [""])[0]).decode("utf-8", "replace"))
            except ValueError:
                pass
            self.send_response(204)
            self.end_headers()
            return
        if url.path != "/arm":
            self.send_error(404)
            return
        qs = parse_qs(url.query)
        _learn(_hex(qs, "tail20"), _hex(qs, "udid"), _hex(qs, "tail50"))
        body = keys.public_key().hex().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start() -> None:
    _load_tail20()
    httpd = ThreadingHTTPServer((HOST, PORT), _Handler)
    threading.Thread(target=httpd.serve_forever, name="jp-arming", daemon=True).start()
    log.info("JP arming side channel on %s:%d (pubkey %s..)", HOST, PORT, keys.public_key().hex()[:16])
