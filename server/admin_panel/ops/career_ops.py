"""The in-progress career. Everything that moves the run (turn, races, events,
park/resume) is career.py's / admin.py's own command, called in-process, so
the reconcile rules those tools learned the hard way still hold. Plain
property edits go through career._reconcile afterwards for the same reason."""

from __future__ import annotations

import json
from types import SimpleNamespace

import admin as ADMIN
import career as CAREER
from app import career_events as CE
from app import scenarios
from app.handlers import single_mode_team as T

from . import op
from .catalog import program_catalog
from .common import STATS, OpError, card_name, load, save, text


def _race_name(pid) -> str:
    return next((p["name"] for p in program_catalog() if p["id"] == pid), f"Program {pid}")


def _goals(ci, history):
    goals = T._route_all_goals(tuple(ci.get("route_race_id_array") or ()))
    out = []
    for g in goals:
        turn, sort_id, ctype, cid, cv1, cv2 = g
        if ctype == 1:
            what = _race_name(cid)
        elif ctype == 2:
            after, by = T._goal_window(g, goals)
            what = f"{T._grade_tally(g, history, goals)}/{cv2} top-{cv1} finishes in grade {cid} races (turns {after + 1}-{by})"
        else:
            what = f"{cv1:,} fans"
        out.append({"turn": turn, "sort": sort_id, "kind": {1: "race", 2: "tally", 3: "fans"}.get(ctype, str(ctype)),
                    "what": what, "cleared": bool(T._goal_is_cleared(g, ci, history, goals)),
                    "due": turn <= (ci.get("turn") or 0)})
    return out


def _bonds(ci):
    supports = {s.get("position"): s for s in ci.get("support_card_array") or []}
    out = []
    for e in ci.get("evaluation_info_array") or []:
        tid = e.get("target_id")
        s = supports.get(tid)
        name = (text(75, s.get("support_card_id")) if s else "") or (f"NPC {tid}" if tid and tid > 6 else f"Slot {tid}")
        out.append({"target_id": tid, "evaluation": e.get("evaluation"), "name": name,
                    "support_card_id": s.get("support_card_id") if s else None,
                    "is_outing": e.get("is_outing"), "story_step": e.get("story_step")})
    return out


@op("career.state")
def state(viewer, args):
    full_state = load(viewer)
    slots = sorted((full_state.get(ADMIN.CAREER_SLOTS_KEY) or {}).items())
    parked = []
    for name, blob in slots:
        ci = ((blob.get(T.STATE_KEY) or {}).get("data", {}) or {}).get("chara_info", {}) or {}
        parked.append({"name": name, "card_id": ci.get("card_id"), "card": card_name(ci.get("card_id")),
                       "turn": ci.get("turn")})
    career = full_state.get(T.STATE_KEY)
    if not isinstance(career, dict) or not isinstance(career.get("data"), dict):
        return {"active": False, "parked": parked}
    data = career["data"]
    ci = data["chara_info"]
    turn = ci.get("turn") or 1
    history = data.get("race_history") or []
    st = CE.state(full_state)
    scen = scenarios.get(ci.get("scenario_id")) if hasattr(scenarios, "get") else None
    scen_keys = [k for k in (getattr(scen, "state_keys", ()) or ()) if k in full_state]
    home = data.get("home_info") or {}
    forced = sorted(T._forced_race_turns(tuple(ci.get("route_race_id_array") or ())))
    return {
        "active": True, "parked": parked,
        "chara_info": ci, "card": card_name(ci.get("card_id")),
        "turn_label": CAREER._turn_label(turn),
        "state_name": CAREER.STATE_NAMES.get(ci.get("state"), "?"),
        "scenario_name": getattr(scen, "name", None) or T.SCENARIO_NAMES.get(ci.get("scenario_id"), "?"),
        "scenario_keys": scen_keys,
        "goals": _goals(ci, history),
        "goals_cleared": T._goals_cleared_count(ci, history, turn),
        "races": [{**h, "name": _race_name(h.get("program_id"))} for h in history],
        "forced_turns": [t for t in forced if t >= turn],
        "facility_levels": T._facility_levels(data),
        "camp": bool(T._is_camp_turn(turn)),
        "commands": [{"id": c.get("command_id"), "enabled": bool(c.get("is_enable")),
                      "level": c.get("level")} for c in home.get("command_info_array") or []],
        "race_entry_restriction": home.get("race_entry_restriction"),
        "events": {"active": st.get("active"), "queue": st.get("queue") or [],
                   "fired": [{"key": k, "turn": CAREER._once_key_turn(k)} for k in st.get("fired") or []]},
        "in_flight": [k for k in CAREER._transient_keys() if k in full_state],
        "bonds": _bonds(ci),
        "end_turn": CAREER.CAREER_END_TURN,
    }


# chara_info fields that only move through a command (turn needs the full
# reconcile + ledger rewind of set-turn).
_COMMAND_ONLY = {"turn"}


@op("career.patch", label="Career: edit {fields}")
def patch(viewer, args):
    full_state = load(viewer)
    career = full_state.get(T.STATE_KEY)
    if not isinstance(career, dict) or not isinstance(career.get("data"), dict):
        raise OpError("No active career.")
    ci = career["data"]["chara_info"]
    fields = args.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise OpError("Nothing to change.")
    bad = _COMMAND_ONLY & set(fields)
    if bad:
        raise OpError("Use Set turn to move the turn (it reconciles goals, races and events).")
    for k, v in fields.items():
        if k in STATS or k.startswith("max_") or k in ("skill_point", "fans", "vital", "motivation", "chara_grade"):
            v = int(v)
        ci[k] = v
    notes = CAREER._reconcile(full_state, career, grade=bool(args.get("regrade")))
    save(viewer, full_state)
    return {"changed": sorted(fields), "notes": notes}


@op("career.data_patch", label="Career: edit {path}")
def data_patch(viewer, args):
    """Set one dotted path in the career's data (career.py `set`), or with
    full_state in the whole viewer state, then reconcile."""
    v = args.get("value")
    ns = SimpleNamespace(path=str(args.get("path") or ""), value=v if isinstance(v, str) else json.dumps(v),
                         create=bool(args.get("create")), full_state=bool(args.get("full_state")))
    CAREER.cmd_set(viewer, ns)
    return {"ok": True}


# career.py / admin.py commands and their argparse defaults.
_CMDS = {
    "set_turn": (CAREER.cmd_set_turn, dict(value=None, fill_races=False, rank=1, with_rewards=False, keep_races=False,
                                           keep_events=False, reset_fired=False, mark_past=False, playing_state=1)),
    "reconcile": (CAREER.cmd_reconcile, dict(clear_flight=False, no_grade=False)),
    "event_undo": (CAREER.cmd_event_undo, dict(keys=[], turn=None, all=False)),
    "event_done": (CAREER.cmd_event_done, dict(keys=[])),
    "event_drop": (CAREER.cmd_event_drop, dict(event_id=None, all=False)),
    "event_queue": (CAREER.cmd_event_queue, dict(event_id=None, story=None, choices=1, timing=1, chara=None,
                                                 priority=CE.PRIO_NORMAL, once_key=None)),
    "race_add": (CAREER.cmd_race_add, dict(program_id=None, turn=None, rank=1, with_rewards=False)),
    "race_del": (CAREER.cmd_race_del, dict(turn=None, from_turn=None, all=False, refund_fans=False)),
    "unlock": (CAREER.cmd_unlock, dict(command=[], all=False, lock=False)),
    "park": (ADMIN.cmd_career_park, dict(name=None, force=False)),
    "resume": (ADMIN.cmd_career_resume, dict(name=None)),
    "idle_complete": (ADMIN.cmd_idle_career_complete, dict()),
    "add_skill": (ADMIN.cmd_add_skill, dict(value=None, level=1)),
    "set_bond": (ADMIN.cmd_set_bond, dict(name=None, value=None)),
}


@op("career.cmd", label="Career: {cmd}")
def cmd(viewer, args):
    name = args.get("cmd")
    if name == "abandon":
        if not args.get("confirm"):
            raise OpError("Confirm abandoning the career.")
        removed = T.clear_active_career(viewer)
        print(f"removed {len(removed)} career key(s)")
        return {"removed": removed}
    if name == "drop_slot":
        full_state = load(viewer)
        slots = full_state.get(ADMIN.CAREER_SLOTS_KEY) or {}
        if slots.pop(str(args.get("name")), None) is None:
            raise OpError("No such slot.")
        full_state[ADMIN.CAREER_SLOTS_KEY] = slots
        save(viewer, full_state)
        return {"ok": True}
    if name not in _CMDS:
        raise OpError(f"Unknown career command {name}.")
    fn, defaults = _CMDS[name]
    opts = dict(defaults)
    for k, v in (args.get("opts") or {}).items():
        if k in opts:
            opts[k] = v
    missing = [k for k, v in opts.items() if v is None and k in ("value", "program_id", "name", "event_id", "story")
               and not (name == "event_drop" and k == "event_id")]
    if missing:
        raise OpError(f"Missing {', '.join(missing)}.")
    fn(viewer, SimpleNamespace(**opts))
    return {"ok": True}
