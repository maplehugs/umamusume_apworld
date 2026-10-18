"""Archipelago: the room settings (client_config.json), the game server's
connection state (archipelago_status.json) and the played account's progress:
tracker, goal, buffs, traps and boons, sent and received items, hints."""

from __future__ import annotations

import json

from app import archipelago
from app import state as state_store
from app.archipelago import client, tables
from app.handlers import single_mode_team

from . import op
from .career_tuning import _read, _write
from .common import OpError

KEYS = ("archipelago_server", "archipelago_slot", "archipelago_password")


def _status() -> dict:
    try:
        return json.loads(client.status_path().read_text())
    except (OSError, ValueError):
        return {"state": "off", "detail": "the game server isn't running"}


@op("archipelago.get")
def get(viewer, args):
    cfg = _read()
    status = _status()
    out = {
        "settings": {k: cfg.get(k) for k in KEYS},
        "connection": {"state": status.get("state"), "detail": status.get("detail")},
        "room": status.get("room") or {},
        "item_names": sorted(tables.item_name_to_id()),
        "save": None,
    }
    vid = archipelago.target_viewer()
    full_state = state_store.get_state(vid) if vid else None
    if not full_state or archipelago.AP_KEY not in full_state:
        return out
    st = archipelago.ap_state(full_state)
    names = {v: k for k, v in tables.location_name_to_id().items()}
    out["save"] = {
        "viewer": vid,
        "seed": st.get("seed_name"),
        "items_received": st.get("next_index", 0),
        "checks_done": len(st.get("checked") or ()),
        "recent_checks": [names.get(i, str(i)) for i in (st.get("checked") or ())[-8:]][::-1],
        "next_career": [archipelago.item_name(t) for t in st.get("traps") or ()],
        "different_races_won": len(st.get("races_won") or ()),
    }
    out["tracker"] = archipelago.tracker(full_state)
    out["goal"] = archipelago.goal_progress(full_state)
    out["received"] = [{**r, "info": archipelago.item_info(r.get("item", ""))}
                       for r in reversed((st.get("received") or [])[-200:])]
    out["permanent"] = archipelago.permanent_buffs(full_state)
    # Done checks, newest first, with what they held (only checks already done:
    # the rest of the scout list is a spoiler).
    scouted = st.get("scouted") or {}
    out["sent"] = [{"where": names.get(loc, str(loc)), **scouted.get(str(loc), {"item": "?", "to": "", "flags": 0})}
                   for loc in reversed(st.get("checked") or [])][:200]
    for row in out["sent"]:  # another game's item names just match nothing here
        row["info"] = archipelago.item_info(row["item"])
    running = (full_state.get(single_mode_team.STATE_KEY) or {}).get("data") or {}
    out["effects"] = archipelago.effects_report(full_state, running.get("chara_info"))
    out["hints"] = [h for h in st.get("hints") or () if h.get("mine_to_find") or h.get("for_me")]
    return out


@op("archipelago.set")
def set_(viewer, args):
    data = _read()
    for k, v in (args.get("values") or {}).items():
        if k not in KEYS:
            raise OpError(f"Unknown setting {k}.")
        data[k] = str(v).strip() or None
    _write(data)
    return get(viewer, {})


@op("archipelago.say")
def say(viewer, args):
    """A chat line or room command for the game server's connection to send
    (the hint button sends "!hint <item>")."""
    text = str(args.get("text") or "").strip()[:200]
    if not text:
        raise OpError("Nothing to send.")
    if _status().get("state") != "connected":
        raise OpError("Not connected to the Archipelago room.")
    with client.say_path().open("a") as f:
        f.write(text.replace("\n", " ") + "\n")
    return {"ok": True}
