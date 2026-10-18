"""
Global entry point: the Global wire transport (app/crypto.py) around the
shared request pipeline (app/dispatch.py). JP's entry point is app/jp/server.py.

Run with:
    uvicorn app.main:app --reload --port 8080
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response

from . import crypto
from . import dispatch as pipeline
from . import region
from .admin_lifecycle import lifespan

# This is the GLOBAL server. JP runs as its own process with its own data
# (app/jp/server.py, `./start-server.sh --region jp`); see app/region.py.
if region.PROCESS_REGION != "global":
    raise RuntimeError("app.main is the Global server; JP is app.jp.server")

# Console keeps its level (UMA_LOG_LEVEL, default INFO); the FILE always
# records DEBUG. Diagnosing a live incident used to mean having had the right
# level set before it happened -- the 2026-09-05 debut report had no server-side
# record at all because nothing was ever written to disk.
_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "server.log", maxBytes=20_000_000, backupCount=3, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
logging.basicConfig(level=logging.DEBUG,
                    handlers=[logging.StreamHandler(), _file_handler])
logging.getLogger().handlers[0].setLevel(
    os.environ.get("UMA_LOG_LEVEL", "INFO").upper())
log = logging.getLogger("uma-server")

app = FastAPI(title="Umamusume private server (dev)", lifespan=lifespan)
from . import custom_support, custom_support_http
app.include_router(custom_support_http.router)


@app.post("/{endpoint_path:path}")
async def dispatch(endpoint_path: str, request: Request):
    raw = await request.body()
    decoded = crypto.decode_request(raw, dict(request.headers))
    with custom_support.request_context(dict(request.headers), decoded.payload):
        patched = custom_support.project(pipeline.handle_decoded(endpoint_path, decoded.payload, decoded.sid or None))
    body = crypto.encode_response(patched, decoded.udid_raw)
    # VERIFIED 2026-08-11 against a live real-server capture
    # (tools/capture_proxy.py --upstream real): the real server's
    # Content-Type is "application/x-msgpack; charset=utf-8", not
    # "text/plain". Content itself was independently proven byte-correct
    # (a real captured response replayed verbatim through this exact code
    # path still failed client-side -- see docs/LINUX_LOGIN_FIX.md), so this
    # header is the next remaining, evidence-backed difference between what
    # we send and what the real server sends.
    return Response(content=body, media_type="application/x-msgpack; charset=utf-8")
