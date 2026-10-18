"""JP's plushie collection and its two claw machines: the arcade one reached
from the home screen (plushie/*) and the in-career one after a Recreation
(single_mode*/finish_claw_crane, JP's replacement for Global's
single_mode/minigame_end).

The client runs the whole game -- odds, arm swing, what the claw holds -- from
master.mdb's crane_game_* tables and reports what it caught. The server's part
is the collection and the verdict:

    `WIRE` plushie/finish_claw_crane {plushies: [{get_id, chara_id, dress_id,
    appearance, motion, face}]} -> {result_state, is_new_plushie_contained}.
    One request per credit (CraneGameDefines.GAME_NUM = 3 grabs); get_id
    numbers the catches across the credit.

    `WIRE` plushie/collection {} -> {collected_plushies: [{chara_id, dress_id,
    appearance, count, first_acquired_time}], last_checked_time}. A catch adds
    1 to its (chara_id, dress_id, appearance) row; a new row is stamped with
    the catch's servertime. last_checked_time is the account's stored value
    (it stayed put across both captured plays), moved only by
    plushie/update_last_checked_time.

    `WIRE` load/index new_plushie_exists: true while any row was first
    acquired after last_checked_time (14 such rows on the capture account,
    true on every load/index before and after the plays).
"""

from __future__ import annotations

import copy
import functools
import time

from ... import master_data, scenarios
from ... import state as state_store
from ...handlers import missions, single_mode_team
from ...result_codes import ResultCode, refuse

COLLECTION_KEY = "jp_plushies"
LAST_CHECKED_KEY = "jp_plushie_last_checked_time"

# CraneGameDefines.ServerGameResult. The count thresholds are Global's
# minigame_end rule (0 / 1-5 / 6+, confirmed by four live results there) and
# agree with both JP arcade captures (1 caught -> 2, 8 caught -> 3).
FAILED, SUCCESS, GREAT_SUCCESS, SUCCESS_WITH_BIG, GREAT_SUCCESS_WITH_BIG = 1, 2, 3, 4, 5
_GREAT_SUCCESS_MIN = 6
_BIG = 2                    # CraneGameDefines.PlushieAppearance: 0 Default, 1 Mic, 2 Big
_APPEARANCES = (0, 1, _BIG)
# The in-career outcome story is picked by tier 1-3 (single_mode_story_data.
# mini_game_result); a Big catch is the same story.
_STORY_TIER = {FAILED: 1, SUCCESS: 2, GREAT_SUCCESS: 3,
               SUCCESS_WITH_BIG: 2, GREAT_SUCCESS_WITH_BIG: 3}

_COND_COLLECTION_KINDS = 600040   # コレクションのぬいぐるみをN種類獲得しよう (331400/331410)


def _ok(data: dict) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


def _state(viewer_id) -> dict:
    return state_store.get_state(viewer_id) or {}


def _key(p: dict) -> tuple:
    return (int(p["chara_id"]), int(p["dress_id"]), int(p.get("appearance") or 0))


def _order(row: dict) -> tuple:
    """`WIRE` the real list runs by dress_id (every default dress 2 first,
    then the character dresses), chara_id, appearance."""
    return (row["dress_id"], row["chara_id"], row["appearance"])


@functools.lru_cache(maxsize=4096)
def _dress_chara(dress_id: int) -> int | None:
    row = master_data.query_one("SELECT chara_id FROM dress_data WHERE id=?", (dress_id,))
    return row["chara_id"] if row else None


@functools.lru_cache(maxsize=512)
def _is_chara(chara_id: int) -> bool:
    return master_data.query_one("SELECT id FROM chara_data WHERE id=?", (chara_id,)) is not None


def _valid(plushies) -> bool:
    """Each catch names a real character in a dress that is theirs (or the
    shared default dress, chara_id 0) and a known appearance."""
    if not isinstance(plushies, list):
        return False
    for p in plushies:
        try:
            chara, dress, appearance = _key(p)
        except (KeyError, TypeError, ValueError):
            return False
        if appearance not in _APPEARANCES or not _is_chara(chara):
            return False
        if _dress_chara(dress) not in (0, chara):
            return False
    return True


def result_state(plushies: list) -> int:
    caught = len(plushies)
    if not caught:
        return FAILED
    big = any(int(p.get("appearance") or 0) == _BIG for p in plushies)
    if caught >= _GREAT_SUCCESS_MIN:
        return GREAT_SUCCESS_WITH_BIG if big else GREAT_SUCCESS
    return SUCCESS_WITH_BIG if big else SUCCESS


def record(full_state: dict, plushies: list, now: int) -> bool:
    """Add the catches to the collection; True when one of them was not in it."""
    rows = full_state.setdefault(COLLECTION_KEY, [])
    by_key = {_key(r): r for r in rows}
    new = False
    for p in plushies:
        k = _key(p)
        row = by_key.get(k)
        if row is None:
            row = {"chara_id": k[0], "dress_id": k[1], "appearance": k[2],
                   "count": 0, "first_acquired_time": now}
            rows.append(row)
            by_key[k] = row
            new = True
        row["count"] += 1
    rows.sort(key=_order)
    return new


def new_plushie_exists(full_state: dict) -> bool:
    seen = full_state.get(LAST_CHECKED_KEY) or 0
    return any(r["first_acquired_time"] > seen for r in full_state.get(COLLECTION_KEY) or [])


# ------------------------------------------------------------------- arcade
def handle_collection(payload: dict) -> dict:
    full_state = _state(payload["viewer_id"])
    return _ok({"collected_plushies": copy.deepcopy(full_state.get(COLLECTION_KEY) or []),
                "last_checked_time": full_state.get(LAST_CHECKED_KEY) or 0})


def handle_update_last_checked_time(payload: dict) -> dict:
    """`WIRE` (dump.cs) an empty request and an empty reply."""
    viewer_id = payload["viewer_id"]
    full_state = _state(viewer_id)
    full_state[LAST_CHECKED_KEY] = int(time.time())
    state_store.save_state(viewer_id, full_state)
    return _ok({})


def handle_finish_claw_crane(payload: dict) -> dict:
    plushies = payload.get("plushies") or []
    if not _valid(plushies):
        return refuse(ResultCode.PARAM_ERROR)
    viewer_id = payload["viewer_id"]
    full_state = _state(viewer_id)
    is_new = record(full_state, plushies, int(time.time()))
    state_store.save_state(viewer_id, full_state)
    return _ok({"result_state": result_state(plushies), "is_new_plushie_contained": is_new})


# ------------------------------------------------------------------ in career
def handle_career_finish_claw_crane(payload: dict) -> dict:
    """<family>/finish_claw_crane {plushies, current_turn} -> the career reply
    Global's single_mode/minigame_end builds (chara_info, the outcome story in
    unchecked_event_array, the scenario's data set attached by the dispatch
    chokepoint) plus result_state and is_new_plushie_contained. The catches go
    into the same collection the arcade fills."""
    plushies = payload.get("plushies") or []
    if not _valid(plushies):
        return refuse(ResultCode.PARAM_ERROR)
    state = result_state(plushies)
    viewer_id = payload["viewer_id"]
    full_state = _state(viewer_id)
    if not isinstance(full_state.get(single_mode_team.STATE_KEY), dict):
        # No career: minigame_end's own refusal, before anything is recorded.
        return single_mode_team.handle_minigame_end(payload)
    is_new = record(full_state, plushies, int(time.time()))
    state_store.save_state(viewer_id, full_state)
    resp = single_mode_team.handle_minigame_end(dict(payload, result={
        "result_state": _STORY_TIER[state],
        "result_value": len(plushies),
        "result_detail_array": [{k: p.get(k) for k in ("get_id", "chara_id", "dress_id", "motion", "face")}
                                for p in plushies]}))
    data = resp.get("data")
    if isinstance(data, dict):
        data["result_state"] = state
        data["is_new_plushie_contained"] = is_new
    return resp


def after(endpoint: str, payload: dict, resp: dict) -> None:
    """load/index's home-screen badge, applied to the reply the shared
    pipeline built."""
    if endpoint != "load/index" or (resp.get("data_headers") or {}).get("result_code", 1) != 1:
        return
    data = resp.get("data")
    if isinstance(data, dict):
        data["new_plushie_exists"] = new_plushie_exists(_state(payload.get("viewer_id")))


def _collection_kinds(viewer_id, full_state: dict, row) -> int:
    return len(full_state.get(COLLECTION_KEY) or [])


missions.CONDITION_HOOKS[_COND_COLLECTION_KINDS] = _collection_kinds

HANDLERS = {
    "plushie/collection": handle_collection,
    "plushie/update_last_checked_time": handle_update_last_checked_time,
    "plushie/finish_claw_crane": handle_finish_claw_crane,
    **{f"{s.endpoint_prefix}/finish_claw_crane": handle_career_finish_claw_crane
       for s in scenarios.all_scenarios()},
}
