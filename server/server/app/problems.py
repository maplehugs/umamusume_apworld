"""Problems the game ran into on this run, for the panel to point at a bug report.

A crash in a handler, or a refusal (result_code other than OK) on a career or
race request, lands here; the panel's Archipelago window shows the newest ones
with Report a bug / Download logs. Refusals outside careers (a shop refusing an
exchange, say) are normal game flow and stay out.

Kept in a file next to archipelago_status.json: the panel's ops run in a worker
process, so they can't see this process's memory."""

from __future__ import annotations

import json
import logging
import time

from . import region

log = logging.getLogger("uma-server")

REPORT_URL = "https://uma.5maple.com/report"
_WATCHED = ("single_mode", "team_race", "legend_race", "race_entry", "race_start", "race_end", "race_out")
_KEEP = 20


def _path():
    return region.data_dir() / "problems.json"


def watched(endpoint: str) -> bool:
    return any(w in endpoint for w in _WATCHED)


def recent() -> list:
    try:
        return json.loads(_path().read_text())[-5:]
    except (OSError, ValueError):
        return []


def record(endpoint: str, kind: str, detail: str) -> None:
    log.warning("PROBLEM %s on %s: %s -- if the game froze or showed an error, report it at %s "
                "(attach server/logs/server.log)", kind, endpoint, detail[:300], REPORT_URL)
    try:
        items = json.loads(_path().read_text())
    except (OSError, ValueError):
        items = []
    items.append({"time": time.time(), "endpoint": endpoint, "kind": kind, "detail": detail[:300]})
    try:
        _path().write_text(json.dumps(items[-_KEEP:]))
    except OSError:
        log.exception("could not save problems.json")
