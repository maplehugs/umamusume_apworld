"""Run the loopback admin panel for the lifetime of a PS worker."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys
import threading

from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from . import region, state

log = logging.getLogger("uma-server")


async def panel_redirect(request: Request):
    """GET / is a browser on the game's address: send it to the admin panel."""
    panel = getattr(request.app.state, "admin_panel", None)
    if panel is None:
        return PlainTextResponse("This is the game server (for the Hachimi redirect). The admin panel is off.")
    return RedirectResponse(f"http://localhost:{panel.port}")


@asynccontextmanager
async def lifespan(app):
    # Archipelago: the Legend ladder's events in master.mdb, then the room
    # connection (idles until client_config.json names a room).
    from . import archipelago
    from .archipelago import client as archipelago_client
    if archipelago.is_ap():
        archipelago.sync_legend_events()
    archipelago_client.start()
    try:
        async with _admin_panel(app):
            yield
    finally:
        # Ctrl-C: uvicorn finishes in-flight requests, then lands here. Every
        # save is already committed (state.py is write-through); this folds
        # the WAL back into state.sqlite3 and closes the connections.
        state.close()
        log.info("State saved and closed.")


@asynccontextmanager
async def _admin_panel(app):
    # Uvicorn is normally launched from server/, while admin_panel lives at
    # the repository root. Its subprocess workers still isolate region imports.
    if os.environ.get("UMA_ADMIN_ENABLED", "1").strip().lower() in {"0", "false", "off"}:
        yield
        return
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from admin_panel.server import PanelServer

    port = int(os.environ.get("UMA_ADMIN_PORT", "8190" if region.PROCESS_REGION == "jp" else "8189"))
    if not 0 <= port <= 65535:
        raise ValueError("UMA_ADMIN_PORT must be between 0 and 65535")
    try:
        # Extra Host/Origin names to accept, e.g. a `tailscale serve` front end.
        hosts = [h.strip() for h in os.environ.get("UMA_ADMIN_HOSTS", "").split(",") if h.strip()]
        panel = PanelServer(port, extra_hosts=hosts)
    except OSError as ex:
        raise RuntimeError(
            f"Cannot start admin panel on localhost:{port}. Stop the standalone panel, "
            "set UMA_ADMIN_PORT to a free port, or set UMA_ADMIN_ENABLED=0."
        ) from ex
    thread = threading.Thread(target=panel.serve_forever, name="uma-admin", daemon=True)
    app.state.admin_panel = panel
    thread.start()
    log.info("Admin panel: http://localhost:%s (%s PS)", panel.port, region.PROCESS_REGION)
    try:
        yield
    finally:
        panel.shutdown()
        thread.join()
        panel.pool.close()
        panel.server_close()
        app.state.admin_panel = None
